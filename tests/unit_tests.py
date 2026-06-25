import pytest

from backend.models import EstimateRequest, RiskFlag
from backend.pricing import calculate_price
from backend.risk_agent import analyze_risks
from backend.validators import determine_status


def make_request(**overrides):
    """Small factory for unit tests so each test only changes what it cares about."""
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


def test_pricing_basic_wood_privacy_with_one_walk_gate():
    req = make_request()

    line_items, subtotal, estimated_total, low_range, high_range = calculate_price(req)

    assert subtotal == pytest.approx(4150.0)
    assert estimated_total == pytest.approx(4150.0)
    assert low_range == pytest.approx(3735.0)
    assert high_range == pytest.approx(4772.5)

    labels = [item.label for item in line_items]
    assert "Wood Privacy fence installation" in labels
    assert "Walk gate" in labels


def test_pricing_includes_options_and_complexity_adjustments():
    req = make_request(
        fence_type="vinyl_privacy",
        linear_feet=50.0,
        height_ft=8,
        gate_count=1,
        double_gate_count=1,
        old_fence_removal=True,
        removal_length_feet=25.0,
        material_grade="premium",
        gate_hardware="lockable",
        slope_severity="moderate",
        access_level="limited",
        brush_clearing="moderate",
        stain_seal=True,
        permit_admin=True,
    )

    line_items, subtotal, estimated_total, low_range, high_range = calculate_price(req)

    labels = [item.label for item in line_items]

    assert "Vinyl Privacy fence installation" in labels
    assert "Premium material upgrade" in labels
    assert "Height adjustment above 6 ft (8 ft)" in labels
    assert "Walk gate" in labels
    assert "Double gate" in labels
    assert "Lockable gate hardware" in labels
    assert "Old fence removal" in labels
    assert "Moderate brush clearing" in labels
    assert "Stain or seal option" in labels
    assert "Permit or HOA admin support" in labels
    assert "Moderate slope adjustment" in labels
    assert "Limited access adjustment" in labels

    assert estimated_total > subtotal
    assert low_range == pytest.approx(round(estimated_total * 0.90, 2))
    assert high_range == pytest.approx(round(estimated_total * 1.15, 2))


def test_status_routes_high_risk_to_site_visit():
    req = make_request()
    risks = [
        RiskFlag(
            risk_type="pool_code_review",
            severity="high",
            explanation="Pool fencing requires code review.",
            recommended_action="Require estimator review.",
        )
    ]

    status = determine_status(
        req=req,
        risk_flags=risks,
        missing_questions=[],
        confidence_score=0.90,
    )

    assert status == "site_visit_required"


def test_status_routes_missing_questions_to_customer_info():
    req = make_request()

    status = determine_status(
        req=req,
        risk_flags=[],
        missing_questions=["Does the customer need any gates?"],
        confidence_score=0.90,
    )

    assert status == "needs_customer_info"


def test_status_ready_to_send_when_clean_and_confident():
    req = make_request()

    status = determine_status(
        req=req,
        risk_flags=[],
        missing_questions=[],
        confidence_score=0.95,
    )

    assert status == "ready_to_send"


def test_rule_based_risk_agent_flags_hoa_pets_timeline_and_removal(monkeypatch):
    # Keep this as a true unit test by disabling the optional LLM merge path.
    import backend.risk_agent as risk_agent_module

    monkeypatch.setattr(risk_agent_module, "analyze_risks_with_llm", None)

    req = make_request(
        old_fence_removal=True,
        gate_count=0,
        customer_notes="HOA neighborhood. We have two dogs and want this done quickly.",
    )

    risks, missing_questions, confidence_score = analyze_risks(req)
    risk_types = {risk.risk_type for risk in risks}
    questions_text = "\n".join(missing_questions).lower()

    assert "old_fence_removal" in risk_types
    assert "hoa_approval" in risk_types
    assert "pet_containment" in risk_types
    assert "timeline_pressure" in risk_types

    assert "hoa" in questions_text
    assert "pets" in questions_text or "pet" in questions_text
    assert "timeline" in questions_text
    assert "gate" in questions_text
    assert 0.35 <= confidence_score <= 1.0
