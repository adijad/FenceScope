"""
Workflow-level integration tests for FenceScope AI.

These tests exercise the FastAPI routes as an integrated workflow while stubbing
external side effects: Postgres writes, SMTP email, LLMs, and compliance lookup.

Place this file at:
    tests/test_integration_workflows.py

Run with:
    pytest -q tests/test_integration_workflows.py
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


def _import_backend_main(monkeypatch):
    """
    Import the FastAPI module after setting test env vars.

    The project normally uses backend.main. The fallback to main makes the test
    a little more forgiving if someone runs it from a flattened demo folder.
    """
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5432/test_fencescope",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    try:
        return importlib.import_module("backend.main")
    except ModuleNotFoundError:
        return importlib.import_module("main")


@pytest.fixture()
def api(monkeypatch):
    """
    Create a FastAPI TestClient without touching the real database on startup.
    """
    main = _import_backend_main(monkeypatch)
    monkeypatch.setattr(main, "init_db", lambda: None)

    with TestClient(main.app) as client:
        yield client, main


def test_customer_workflow_precheck_questions_estimate_and_summary_email(api, monkeypatch):
    """
    Customer workflow integration test.

    Covers:
    1. Compliance pre-check from customer payload.
    2. Missing-question/risk review.
    3. Estimate generation with persistence handoff.
    4. Customer-safe preliminary estimate summary email.
    """
    client, main = api
    captured = {}

    def fake_compliance_report(request):
        captured["precheck_request_address"] = request.address
        return main.ComplianceReport(
            matched=True,
            jurisdiction="Blacksburg, VA",
            jurisdiction_id="va_blacksburg",
            overall="PASS",
            findings=[
                {
                    "rule_id": "back-yard-height",
                    "status": "pass",
                    "explanation": "Back-yard fence height is allowed in this demo jurisdiction.",
                    "verbatim_text": "Fences may be erected in rear yards.",
                    "source_url": "https://example.com/blacksburg-fence-rules",
                    "confidence": 0.95,
                }
            ],
            summary="Back yard section passed local fence-code pre-check.",
            needs_human_review=False,
            review_reasons=[],
            source_url="https://example.com/blacksburg-fence-rules",
        )

    def fake_analyze_risks(request):
        captured["questions_request_notes"] = request.customer_notes
        return (
            [
                {
                    "risk_type": "hoa_approval",
                    "severity": "medium",
                    "explanation": "Customer notes mention an HOA.",
                    "recommended_action": "Confirm HOA approval before final quote.",
                }
            ],
            ["Has HOA approval already been obtained for this fence type, height, and color?"],
            0.78,
        )

    def fake_run_estimate_workflow(request):
        captured["estimate_request"] = request
        return main.EstimateResult(
            customer_name=request.customer_name,
            address=request.address,
            total_feet=request.linear_feet,
            line_items=[
                {
                    "label": "Wood Privacy fence installation",
                    "quantity": request.linear_feet,
                    "unit": "linear feet",
                    "unit_cost": 38.0,
                    "total": 7068.0,
                },
                {
                    "label": "Walk gate",
                    "quantity": 2,
                    "unit": "each",
                    "unit_cost": 350.0,
                    "total": 700.0,
                },
            ],
            subtotal=7768.0,
            estimated_total=7768.0,
            low_range=6991.2,
            high_range=8933.2,
            risk_flags=[
                {
                    "risk_type": "hoa_approval",
                    "severity": "medium",
                    "explanation": "Customer notes mention an HOA.",
                    "recommended_action": "Confirm HOA approval before final quote.",
                }
            ],
            missing_questions=[],
            confidence_score=0.82,
            status="needs_estimator_review",
            customer_proposal="Customer-facing preliminary proposal draft.",
            internal_notes="Estimator should confirm HOA approval before final quote.",
        )

    def fake_create_customer(name, email, phone, address):
        captured["created_customer"] = {
            "name": name,
            "email": email,
            "phone": phone,
            "address": address,
        }
        return {
            "id": 101,
            "name": name,
            "email": email,
            "phone": phone,
            "address": address,
        }

    def fake_create_estimate(customer_id, request_data, compliance_report, estimate_result):
        captured["created_estimate"] = {
            "customer_id": customer_id,
            "request_data": request_data,
            "compliance_report": compliance_report,
            "estimate_result": estimate_result,
        }
        return {"id": 202}

    def fake_send_estimate_summary_email(**kwargs):
        captured["summary_email"] = kwargs
        return {
            "sent": True,
            "to_email": kwargs["to_email"],
            "subject": f"Your FenceScope preliminary estimate for {kwargs['address']}",
            "body_preview": "Customer-safe preliminary summary only.",
        }

    monkeypatch.setattr(main, "run_compliance_for_estimate_request", fake_compliance_report)
    monkeypatch.setattr(main, "analyze_risks", fake_analyze_risks)
    monkeypatch.setattr(main, "run_estimate_workflow", fake_run_estimate_workflow)
    monkeypatch.setattr(main, "create_customer", fake_create_customer)
    monkeypatch.setattr(main, "create_estimate", fake_create_estimate)
    monkeypatch.setattr(main, "send_estimate_summary_email", fake_send_estimate_summary_email)

    customer_payload = {
        "customer_name": "Sarah Miller",
        "customer_email": "sarah@example.com",
        "customer_phone": "(540) 555-0198",
        "address": "888 Patrick Henry Dr, Blacksburg, VA 24060, USA",
        "property_lat": 37.2296,
        "property_lng": -80.4139,
        "fence_type": "wood_privacy",
        "height_ft": 6,
        "linear_feet": 186.0,
        "yard_location": "back",
        "yard_sections": [
            {"location": "back", "included": True, "height_ft": 6, "linear_feet": 186.0}
        ],
        "gate_count": 2,
        "double_gate_count": 0,
        "old_fence_removal": True,
        "difficult_access": False,
        "slope_present": True,
        "material_grade": "standard",
        "gate_hardware": "standard",
        "removal_length_feet": 186.0,
        "slope_severity": "moderate",
        "access_level": "easy",
        "brush_clearing": "none",
        "stain_seal": False,
        "permit_admin": False,
        "customer_notes": "Backyard slopes slightly. HOA neighborhood. Wants quote quickly.",
    }

    precheck_response = client.post("/precheck", json=customer_payload)
    assert precheck_response.status_code == 200
    precheck_data = precheck_response.json()
    assert precheck_data["overall"] == "PASS"
    assert precheck_data["jurisdiction_id"] == "va_blacksburg"
    assert precheck_data["findings"][0]["status"] == "pass"

    questions_response = client.post("/questions", json=customer_payload)
    assert questions_response.status_code == 200
    questions_data = questions_response.json()
    assert questions_data["confidence_score"] == 0.78
    assert questions_data["risk_flags"][0]["risk_type"] == "hoa_approval"
    assert "HOA approval" in questions_data["missing_questions"][0]

    estimate_payload = {
        **customer_payload,
        "missing_answers": {
            "Has HOA approval already been obtained for this fence type, height, and color?":
                "Customer says HOA approval is in progress."
        },
    }

    estimate_response = client.post("/estimate", json=estimate_payload)
    assert estimate_response.status_code == 200
    estimate_data = estimate_response.json()
    assert estimate_data["customer_id"] == 101
    assert estimate_data["estimate_id"] == 202
    assert estimate_data["estimated_total"] == 7768.0
    assert estimate_data["status"] == "needs_estimator_review"
    assert estimate_data["compliance_report"]["overall"] == "PASS"

    assert captured["created_customer"]["email"] == "sarah@example.com"
    assert captured["created_estimate"]["customer_id"] == 101
    assert captured["created_estimate"]["request_data"]["yard_sections"][0]["location"] == "back"
    assert captured["created_estimate"]["estimate_result"]["internal_notes"].startswith("Estimator")

    summary_email_payload = {
        "to_email": "sarah@example.com",
        "customer_name": "Sarah Miller",
        "address": estimate_data["address"],
        "estimate_id": estimate_data["estimate_id"],
        "estimated_total": estimate_data["estimated_total"],
        "low_range": estimate_data["low_range"],
        "high_range": estimate_data["high_range"],
        "status": estimate_data["status"],
        "confidence_score": estimate_data["confidence_score"],
        "compliance_overall": estimate_data["compliance_report"]["overall"],
        "compliance_jurisdiction": estimate_data["compliance_report"]["jurisdiction"],
        "remaining_questions": estimate_data["missing_questions"],
    }

    email_response = client.post("/email/estimate-summary", json=summary_email_payload)
    assert email_response.status_code == 200
    email_data = email_response.json()
    assert email_data["sent"] is True
    assert email_data["to_email"] == "sarah@example.com"
    assert captured["summary_email"]["estimate_id"] == 202
    assert captured["summary_email"]["compliance_overall"] == "PASS"


def test_admin_workflow_load_queue_save_decision_and_send_email(api, monkeypatch):
    """
    Admin workflow integration test.

    Covers:
    1. Loading the saved estimate review queue.
    2. Saving estimator review decision, notes, and edited email draft.
    3. Sending the admin-approved customer email and marking the estimate as sent.
    """
    client, main = api
    captured = {"sent_estimate_ids": []}

    saved_estimate = {
        "id": 202,
        "created_at": "2026-06-25T10:00:00",
        "customer_id": 101,
        "customer_name": "Sarah Miller",
        "customer_email": "sarah@example.com",
        "customer_phone": "(540) 555-0198",
        "address": "888 Patrick Henry Dr, Blacksburg, VA 24060, USA",
        "fence_type": "wood_privacy",
        "yard_location": "back",
        "yard_sections": [
            {"location": "back", "included": True, "height_ft": 6, "linear_feet": 186.0}
        ],
        "height_ft": 6,
        "linear_feet": 186.0,
        "estimated_total": 7768.0,
        "low_range": 6991.2,
        "high_range": 8933.2,
        "confidence_score": 0.82,
        "status": "needs_estimator_review",
        "missing_answers": {
            "Has HOA approval already been obtained for this fence type, height, and color?":
                "Customer says HOA approval is in progress."
        },
        "admin_decision": "under_review",
        "admin_decision_notes": None,
        "admin_email_subject": None,
        "admin_email_body": None,
        "admin_email_sent": False,
        "admin_email_sent_at": None,
        "admin_updated_at": None,
        "compliance_report": {
            "matched": True,
            "jurisdiction": "Blacksburg, VA",
            "jurisdiction_id": "va_blacksburg",
            "overall": "PASS",
            "findings": [],
            "summary": "Back yard section passed local fence-code pre-check.",
            "needs_human_review": False,
            "review_reasons": [],
        },
        "estimate_result": {
            "customer_name": "Sarah Miller",
            "address": "888 Patrick Henry Dr, Blacksburg, VA 24060, USA",
            "total_feet": 186.0,
            "line_items": [
                {
                    "label": "Wood Privacy fence installation",
                    "quantity": 186.0,
                    "unit": "linear feet",
                    "unit_cost": 38.0,
                    "total": 7068.0,
                }
            ],
            "subtotal": 7768.0,
            "estimated_total": 7768.0,
            "low_range": 6991.2,
            "high_range": 8933.2,
            "risk_flags": [
                {
                    "risk_type": "hoa_approval",
                    "severity": "medium",
                    "explanation": "Customer notes mention an HOA.",
                    "recommended_action": "Confirm HOA approval before final quote.",
                }
            ],
            "missing_questions": [],
            "confidence_score": 0.82,
            "status": "needs_estimator_review",
            "customer_proposal": "Customer-facing preliminary proposal draft.",
            "internal_notes": "Estimator should confirm HOA approval before final quote.",
        },
        "customer_proposal": "Customer-facing preliminary proposal draft.",
        "internal_notes": "Estimator should confirm HOA approval before final quote.",
    }

    def fake_get_all_estimates():
        return [saved_estimate]

    def fake_update_admin_decision(
        estimate_id,
        admin_decision,
        admin_decision_notes,
        admin_email_subject,
        admin_email_body,
    ):
        captured["admin_decision_update"] = {
            "estimate_id": estimate_id,
            "admin_decision": admin_decision,
            "admin_decision_notes": admin_decision_notes,
            "admin_email_subject": admin_email_subject,
            "admin_email_body": admin_email_body,
        }
        return {
            **saved_estimate,
            "admin_decision": admin_decision,
            "admin_decision_notes": admin_decision_notes,
            "admin_email_subject": admin_email_subject,
            "admin_email_body": admin_email_body,
        }

    def fake_send_admin_approved_proposal_email(to_email, subject, body):
        captured["admin_email"] = {
            "to_email": to_email,
            "subject": subject,
            "body": body,
        }
        return {
            "sent": True,
            "to_email": to_email,
            "subject": subject,
            "body_preview": body,
        }

    def fake_mark_admin_email_sent(estimate_id):
        captured["sent_estimate_ids"].append(estimate_id)
        return {
            **saved_estimate,
            "admin_email_sent": True,
            "admin_email_sent_at": "2026-06-25T10:05:00",
        }

    monkeypatch.setattr(main, "get_all_estimates", fake_get_all_estimates)
    monkeypatch.setattr(main, "update_admin_decision", fake_update_admin_decision)
    monkeypatch.setattr(main, "send_admin_approved_proposal_email", fake_send_admin_approved_proposal_email)
    monkeypatch.setattr(main, "mark_admin_email_sent", fake_mark_admin_email_sent)

    queue_response = client.get("/estimates")
    assert queue_response.status_code == 200
    queue_data = queue_response.json()
    assert len(queue_data) == 1
    assert queue_data[0]["id"] == 202
    assert queue_data[0]["admin_decision"] == "under_review"
    assert queue_data[0]["estimate_result"]["risk_flags"][0]["risk_type"] == "hoa_approval"

    decision_payload = {
        "admin_decision": "approved_to_send",
        "admin_decision_notes": "Estimator reviewed HOA note. Send as preliminary estimate only.",
        "admin_email_subject": "Your preliminary fence estimate is ready",
        "admin_email_body": "Hi Sarah, your preliminary fence estimate is ready for review.",
    }

    decision_response = client.patch(
        "/estimates/202/admin-decision",
        json=decision_payload,
    )
    assert decision_response.status_code == 200
    decision_data = decision_response.json()
    assert decision_data["admin_decision"] == "approved_to_send"
    assert decision_data["admin_email_subject"] == decision_payload["admin_email_subject"]
    assert captured["admin_decision_update"]["estimate_id"] == 202
    assert captured["admin_decision_update"]["admin_decision_notes"].startswith("Estimator reviewed")

    send_payload = {
        "estimate_id": 202,
        "to_email": "sarah@example.com",
        "subject": decision_payload["admin_email_subject"],
        "body": decision_payload["admin_email_body"],
    }

    send_response = client.post("/email/admin-approved-proposal", json=send_payload)
    assert send_response.status_code == 200
    send_data = send_response.json()
    assert send_data["sent"] is True
    assert send_data["to_email"] == "sarah@example.com"
    assert captured["admin_email"]["subject"] == "Your preliminary fence estimate is ready"
    assert captured["sent_estimate_ids"] == [202]
