"""
Unit tests for the AI-safety and production-safeguard layer.

These tests intentionally avoid real LLM, SMTP, database, and compliance-service calls.
They check that FenceScope fails safely, deduplicates model outputs, keeps human-review
boundaries, and does not let failed compliance move into estimate generation.
"""

import pytest
from fastapi import HTTPException

from backend.models import EstimateRequest, LineItem, RiskFlag


def make_request(**overrides):
    """Small valid EstimateRequest factory for unit tests."""
    base = {
        "customer_name": "Test Customer",
        "customer_email": "test@example.com",
        "customer_phone": "555-0100",
        "address": "888 Patrick Henry Dr, Blacksburg, VA 24060, USA",
        "property_lat": 37.2296,
        "property_lng": -80.4139,
        "yard_location": "back",
        "yard_sections": [
            {
                "location": "back",
                "included": True,
                "height_ft": 6,
                "linear_feet": 100.0,
            }
        ],
        "fence_type": "wood_privacy",
        "height_ft": 6,
        "linear_feet": 100.0,
        "gate_count": 1,
        "double_gate_count": 0,
        "old_fence_removal": False,
        "difficult_access": False,
        "slope_present": False,
        "customer_notes": "Backyard fence project.",
        "material_grade": "standard",
        "gate_hardware": "standard",
        "removal_length_feet": 0.0,
        "slope_severity": "none",
        "access_level": "easy",
        "brush_clearing": "none",
        "stain_seal": False,
        "permit_admin": False,
        "missing_answers": {},
    }
    base.update(overrides)
    return EstimateRequest(**base)


def sample_line_items():
    return [
        LineItem(
            label="Wood Privacy fence installation",
            quantity=100,
            unit="linear feet",
            unit_cost=38,
            total=3800,
        ),
        LineItem(
            label="Walk gate",
            quantity=1,
            unit="each",
            unit_cost=350,
            total=350,
        ),
    ]


# ---------------------------------------------------------------------------
# Proposal / LLM safeguards
# ---------------------------------------------------------------------------


def test_proposal_falls_back_when_openai_is_not_configured(monkeypatch):
    import backend.proposal_agent as proposal_agent

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(proposal_agent, "OpenAI", None)

    req = make_request()

    customer_proposal, internal_notes = proposal_agent.draft_proposal(
        req=req,
        line_items=sample_line_items(),
        estimated_total=4150.0,
        low_range=3735.0,
        high_range=4772.5,
        risk_flags=[],
        missing_questions=[],
        status="ready_to_send",
    )

    assert "preliminary estimate" in customer_proposal.lower()
    assert "final quote" in customer_proposal.lower()
    assert "$4,150.00" in customer_proposal
    assert "$3,735.00 to $4,772.50" in customer_proposal
    assert "Estimate status: ready_to_send" in internal_notes



def test_proposal_falls_back_when_llm_call_fails(monkeypatch):
    import backend.proposal_agent as proposal_agent

    class FakeCompletions:
        def create(self, *args, **kwargs):
            raise RuntimeError("LLM provider unavailable")

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(proposal_agent, "OpenAI", FakeOpenAI)

    req = make_request(customer_notes="HOA neighborhood. Customer wants quote quickly.")

    customer_proposal, internal_notes = proposal_agent.draft_proposal(
        req=req,
        line_items=sample_line_items(),
        estimated_total=4150.0,
        low_range=3735.0,
        high_range=4772.5,
        risk_flags=[
            RiskFlag(
                risk_type="hoa_approval",
                severity="medium",
                explanation="HOA approval may be required.",
                recommended_action="Confirm HOA approval before scheduling.",
            )
        ],
        missing_questions=["Has HOA approval already been obtained?"],
        status="needs_estimator_review",
    )

    assert "Has HOA approval already been obtained?" in customer_proposal
    assert "hoa_approval" in internal_notes
    assert "LLM provider unavailable" not in customer_proposal



def test_proposal_system_prompt_contains_no_invention_safeguards():
    import backend.proposal_agent as proposal_agent

    prompt = proposal_agent.SYSTEM_PROMPT.lower()

    assert "do not invent prices" in prompt
    assert "do not invent measurements" in prompt
    assert "do not promise this is a final quote" in prompt
    assert "return valid json only" in prompt


# ---------------------------------------------------------------------------
# Risk-agent safeguards
# ---------------------------------------------------------------------------


def test_risk_agent_falls_back_to_rules_when_llm_risk_analysis_fails(monkeypatch):
    import backend.risk_agent as risk_agent

    def broken_llm_agent(req):
        raise RuntimeError("LLM risk model failed")

    monkeypatch.setattr(risk_agent, "analyze_risks_with_llm", broken_llm_agent)

    req = make_request(
        customer_notes="HOA neighborhood with two dogs. Customer wants this done quickly.",
    )

    risks, missing_questions, confidence_score = risk_agent.analyze_risks(req)
    risk_types = {risk.risk_type for risk in risks}
    question_text = "\n".join(missing_questions).lower()

    assert "hoa_approval" in risk_types
    assert "pet_containment" in risk_types
    assert "timeline_pressure" in risk_types
    assert "hoa" in question_text
    assert 0.35 <= confidence_score <= 1.0



def test_risk_agent_removes_questions_already_answered_by_customer(monkeypatch):
    import backend.risk_agent as risk_agent

    monkeypatch.setattr(risk_agent, "analyze_risks_with_llm", None)

    hoa_question = "Has HOA approval already been obtained for this fence type, height, and color?"

    req = make_request(
        customer_notes="HOA neighborhood.",
        missing_answers={
            hoa_question: "Yes, HOA approval has been obtained.",
        },
    )

    risks, missing_questions, confidence_score = risk_agent.analyze_risks(req)

    assert any(risk.risk_type == "hoa_approval" for risk in risks)
    assert hoa_question not in missing_questions
    assert 0.35 <= confidence_score <= 1.0



def test_merge_risk_flags_normalizes_aliases_and_keeps_higher_severity():
    import backend.risk_agent as risk_agent

    rule_risks = [
        RiskFlag(
            risk_type="hoa",
            severity="low",
            explanation="HOA mentioned.",
            recommended_action="Ask about HOA.",
        )
    ]
    llm_risks = [
        RiskFlag(
            risk_type="hoa_required",
            severity="medium",
            explanation="HOA approval may be required.",
            recommended_action="Confirm approval before installation.",
        )
    ]

    merged = risk_agent.merge_risk_flags(rule_risks, llm_risks)

    assert len(merged) == 1
    assert merged[0].risk_type == "hoa_approval"
    assert merged[0].severity == "medium"
    assert "approval" in merged[0].explanation.lower()



def test_merge_questions_deduplicates_semantically_equivalent_questions():
    import backend.risk_agent as risk_agent

    rule_questions = [
        "Has HOA approval already been obtained for this fence type, height, and color?"
    ]
    llm_questions = [
        "Has HOA approval been obtained for the fence installation?"
    ]

    merged = risk_agent.merge_questions(rule_questions, llm_questions)

    assert len(merged) == 1
    assert "HOA" in merged[0]


# ---------------------------------------------------------------------------
# Compliance and jurisdiction safeguards
# ---------------------------------------------------------------------------


def test_unknown_jurisdiction_does_not_guess_rule_database_match():
    from compliance.jurisdiction import resolve_jurisdiction

    result = resolve_jurisdiction("100 Main St, Richmond, VA 23219, USA")

    assert result["matched"] is False
    assert result["jurisdiction_id"] is None
    assert result["city"] == "richmond"
    assert result["state"] == "va"



def test_compliance_multi_section_failure_blocks_overall_report(monkeypatch):
    import backend.main as main
    from compliance.schemas import ComplianceReport, Finding

    req = make_request(
        yard_sections=[
            {"location": "back", "included": True, "height_ft": 6, "linear_feet": 80.0},
            {"location": "front", "included": True, "height_ft": 6, "linear_feet": 20.0},
        ]
    )

    def fake_check_compliance(spec):
        if spec.location == "front":
            return ComplianceReport(
                matched=True,
                jurisdiction="Blacksburg, VA",
                jurisdiction_id="va_blacksburg",
                overall="FAIL",
                findings=[
                    Finding(
                        rule_id="fence-height-front-yard",
                        status="fail",
                        explanation="Front yard fence is too tall.",
                        confidence=0.95,
                    )
                ],
                summary="Front yard failed.",
                needs_human_review=True,
                review_reasons=["Front yard height issue."],
            )

        return ComplianceReport(
            matched=True,
            jurisdiction="Blacksburg, VA",
            jurisdiction_id="va_blacksburg",
            overall="PASS",
            findings=[
                Finding(
                    rule_id="default-height",
                    status="pass",
                    explanation="Back yard height is allowed.",
                    confidence=0.95,
                )
            ],
            summary="Back yard passed.",
        )

    monkeypatch.setattr(main, "check_compliance", fake_check_compliance)

    report = main.run_compliance_for_estimate_request(req)

    assert report.overall == "FAIL"
    assert report.needs_human_review is True
    assert any(finding.rule_id == "front-fence-height-front-yard" for finding in report.findings)
    assert any("Front yard" in reason for reason in report.review_reasons)



def test_estimate_endpoint_blocks_failed_compliance_before_workflow_or_db(monkeypatch):
    import backend.main as main
    from compliance.schemas import ComplianceReport, Finding

    req = make_request()

    failed_report = ComplianceReport(
        matched=True,
        jurisdiction="Blacksburg, VA",
        jurisdiction_id="va_blacksburg",
        overall="FAIL",
        findings=[
            Finding(
                rule_id="fence-height-front-yard",
                status="fail",
                explanation="Fence is not compliant as entered.",
                confidence=0.95,
            )
        ],
        summary="Compliance failed.",
        needs_human_review=True,
    )

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("Estimate workflow or database write should not run after failed compliance.")

    monkeypatch.setattr(main, "run_compliance_for_estimate_request", lambda request: failed_report)
    monkeypatch.setattr(main, "run_estimate_workflow", should_not_be_called)
    monkeypatch.setattr(main, "create_customer", should_not_be_called)
    monkeypatch.setattr(main, "create_estimate", should_not_be_called)

    with pytest.raises(HTTPException) as exc_info:
        main.create_full_estimate(req)

    assert exc_info.value.status_code == 400
    assert "compliance" in exc_info.value.detail
    assert exc_info.value.detail["compliance"]["overall"] == "FAIL"


# ---------------------------------------------------------------------------
# Email safeguards
# ---------------------------------------------------------------------------


def test_email_send_fails_safely_when_smtp_is_not_configured(monkeypatch):
    import backend.email_service as email_service

    monkeypatch.setattr(email_service, "SMTP_HOST", None)
    monkeypatch.setattr(email_service, "SMTP_USERNAME", None)
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", None)
    monkeypatch.setattr(email_service, "SMTP_FROM_EMAIL", None)

    assert email_service.email_configured() is False

    with pytest.raises(RuntimeError) as exc_info:
        email_service.send_email(
            to_email="customer@example.com",
            subject="Test",
            body="Test body",
        )

    assert "SMTP is not configured" in str(exc_info.value)
