import hmac
import os


from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query, HTTPException, status, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

from compliance.agent import check_compliance
from compliance.schemas import FenceSpec, ComplianceReport

from backend.models import AdminDecisionUpdateRequest, AdminProposalEmailRequest
from backend.storage import update_admin_decision, mark_admin_email_sent
from backend.email_service import send_admin_approved_proposal_email

from backend.address_lookup import (
    autocomplete_address,
    get_place_details,
    search_address,
)
from backend.database import init_db
from backend.models import (
    EstimateRequest,
    EstimateResult,
    MissingQuestionsResult,
    EstimateEmailRequest,
    YardSection,
    IntakeTextRequest,
    IntakeAnalysisResult,
)
from backend.email_service import send_estimate_summary_email
from backend.risk_agent import analyze_risks
from backend.storage import create_customer, create_estimate, get_all_estimates
from backend.workflow import run_estimate_workflow
from backend.intake_agent import analyze_text_intake
from backend.voice_agent import transcribe_project_audio


load_dotenv()
security = HTTPBasic()


app = FastAPI(
    title="FenceScope AI",
    description="AI-assisted estimate triage and proposal workflow for residential fencing companies.",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _admin_auth_error(detail: str = "Admin authentication required."):
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Basic"},
    )


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Protect estimator/admin operations with lightweight HTTP Basic auth.

    This is intentionally simple for the 24-hour demo. It uses ADMIN_USERNAME
    and ADMIN_PASSWORD from .env. In production, replace this with real user
    accounts, hashed passwords, sessions or JWTs, roles, and audit logs.
    """
    expected_username = os.getenv("ADMIN_USERNAME")
    expected_password = os.getenv("ADMIN_PASSWORD")

    if not expected_username or not expected_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin authentication is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD.",
        )

    username_ok = hmac.compare_digest(credentials.username or "", expected_username)
    password_ok = hmac.compare_digest(credentials.password or "", expected_password)

    if not (username_ok and password_ok):
        _admin_auth_error("Invalid admin username or password.")

    return credentials.username


MATERIAL_MAP = {
    "wood_privacy": ("wood", 0),
    "vinyl_privacy": ("vinyl", 0),
    "chain_link": ("chain link", 90),
    "aluminum": ("aluminum", 70),
    "split_rail": ("wood", 70),
}


@app.on_event("startup")
def startup_event():
    init_db()


def section_label(location: str) -> str:
    labels = {
        "front": "Front yard",
        "side": "Side yard",
        "back": "Back yard",
    }
    return labels.get(location, location.title())


def get_compliance_sections(request: EstimateRequest) -> list[YardSection]:
    """
    Returns the yard sections that should be checked for compliance.

    If the user provided a section breakdown, use it.
    Otherwise fall back to the old single yard_location + height_ft behavior.
    """
    if request.yard_sections:
        included_sections = [
            section
            for section in request.yard_sections
            if section.included
        ]

        if included_sections:
            return included_sections

    return [
        YardSection(
            location=request.yard_location,
            included=True,
            height_ft=request.height_ft,
            linear_feet=request.linear_feet,
        )
    ]


def yard_section_to_fence_spec(
    request: EstimateRequest,
    section: YardSection,
) -> FenceSpec:
    material, pct_open = MATERIAL_MAP.get(request.fence_type, ("wood", 0))

    return FenceSpec(
        height_ft=section.height_ft or request.height_ft,
        location=section.location,
        material=material,
        pct_open=pct_open,
        address=request.address,
    )


def run_compliance_for_estimate_request(request: EstimateRequest) -> ComplianceReport:
    """
    Runs compliance for one or more yard sections.

    If multiple sections are present:
    - Any FAIL makes the whole report FAIL.
    - Otherwise any NEEDS_REVIEW makes the whole report NEEDS_REVIEW.
    - Otherwise the whole report PASSes.
    """
    sections = get_compliance_sections(request)

    section_reports = []

    for section in sections:
        spec = yard_section_to_fence_spec(request, section)
        report = check_compliance(spec)
        section_reports.append((section, report))

    if len(section_reports) == 1:
        return section_reports[0][1]

    overall = "PASS"

    if any(report.overall == "FAIL" for _, report in section_reports):
        overall = "FAIL"
    elif any(report.overall == "NEEDS_REVIEW" for _, report in section_reports):
        overall = "NEEDS_REVIEW"

    first_report = section_reports[0][1]

    combined_findings = []
    review_reasons = []

    summary_parts = []

    for section, report in section_reports:
        label = section_label(section.location)
        summary_parts.append(
            f"{label}: {report.overall} at {section.height_ft} ft"
        )

        if report.overall != "PASS":
            review_reasons.append(
                f"{label} returned {report.overall} during compliance pre-check."
            )

        for finding in report.findings:
            finding_data = finding.model_dump()

            finding_data["rule_id"] = (
                f"{section.location}-{finding_data.get('rule_id', 'rule')}"
            )

            finding_data["explanation"] = (
                f"{label} section: {finding_data.get('explanation', '')}"
            )

            combined_findings.append(finding_data)

    summary = (
        f"Checked {len(section_reports)} yard section(s): "
        + "; ".join(summary_parts)
        + "."
    )

    return ComplianceReport(
        matched=any(report.matched for _, report in section_reports),
        jurisdiction=first_report.jurisdiction,
        jurisdiction_id=first_report.jurisdiction_id,
        overall=overall,
        findings=combined_findings,
        summary=summary,
        needs_human_review=overall != "PASS"
        or any(report.needs_human_review for _, report in section_reports),
        review_reasons=review_reasons,
        source_url=first_report.source_url,
        disclaimer=first_report.disclaimer,
    )


@app.get("/")
def root():
    return {
        "message": "FenceScope AI is running",
        "workflow": (
            "estimate intake, map measurement, compliance pre-check, missing-info "
            "collection, pricing, risk review, proposal generation, database history, "
            "and human review status"
        ),
    }


@app.get("/auth/admin-check")
def admin_check(admin_username: str = Depends(require_admin)):
    return {
        "authenticated": True,
        "username": admin_username,
    }


@app.get("/address/search")
def address_search(q: str = Query(..., min_length=3)):
    return {
        "query": q,
        "results": search_address(q),
    }


@app.get("/address/autocomplete")
def address_autocomplete(q: str = Query(..., min_length=2)):
    return {
        "query": q,
        "predictions": autocomplete_address(q),
    }


@app.get("/address/place")
def address_place(place_id: str = Query(..., min_length=3)):
    return {
        "place": get_place_details(place_id),
    }


@app.post("/intake/analyze-text", response_model=IntakeAnalysisResult)
def analyze_intake_text(request: IntakeTextRequest):
    """
    Guardrailed LLM intake endpoint.

    This endpoint:
    1. Classifies whether the text is a fence quote request.
    2. Extracts structured fields from messy customer language.
    3. Identifies missing details and risk hints.
    4. Does not price the job.
    5. Does not save anything.
    6. Does not create an estimate automatically.
    """
    return analyze_text_intake(request)

@app.post("/intake/transcribe-audio")
async def transcribe_audio_intake(audio_file: UploadFile = File(...)):
    """
    Customer-facing endpoint.

    Converts browser microphone recording into transcript text.
    Does not create an estimate.
    Does not run pricing.
    Does not run compliance.
    """

    try:
        return await transcribe_project_audio(audio_file)

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Could not transcribe audio.",
                "error": str(error),
            },
        )
    
@app.post("/questions", response_model=MissingQuestionsResult)
def get_missing_questions(request: EstimateRequest):
    """
    Runs the risk/missing-info pass before pricing.

    This endpoint does not save anything and does not generate an estimate.
    It only identifies questions the customer should answer first.
    """
    risk_flags, missing_questions, confidence_score = analyze_risks(request)

    return MissingQuestionsResult(
        risk_flags=risk_flags,
        missing_questions=missing_questions,
        confidence_score=confidence_score,
    )


@app.post("/compliance/check", response_model=ComplianceReport)
def compliance_check(spec: FenceSpec):
    return check_compliance(spec)


@app.post("/precheck", response_model=ComplianceReport)
def precheck_estimate_request(request: EstimateRequest):
    """
    Runs compliance before pricing or database save.

    This endpoint is for the user-facing workflow step.
    """
    return run_compliance_for_estimate_request(request)


@app.post("/estimate")
def create_full_estimate(request: EstimateRequest):
    """
    Final estimate endpoint.

    This endpoint:
    1. Re-runs compliance as a backend safety guard.
    2. Blocks estimate generation if compliance fails.
    3. Runs the estimate workflow.
    4. Saves customer details.
    5. Saves the full estimate package to Postgres.
    6. Returns the estimate result with customer_id and estimate_id.
    """
    compliance_report = run_compliance_for_estimate_request(request)

    if compliance_report.overall == "FAIL":
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Cannot generate estimate because compliance pre-check failed.",
                "compliance": compliance_report.model_dump(),
            },
        )

    estimate_result: EstimateResult = run_estimate_workflow(request)

    request_data = request.model_dump()
    compliance_data = compliance_report.model_dump()
    estimate_data = estimate_result.model_dump()

    customer = create_customer(
        name=request.customer_name,
        email=request.customer_email or "",
        phone=request.customer_phone or "",
        address=request.address,
    )

    saved_estimate = create_estimate(
        customer_id=customer["id"],
        request_data=request_data,
        compliance_report=compliance_data,
        estimate_result=estimate_data,
    )

    response_payload = {
        **estimate_data,
        "customer_id": customer["id"],
        "estimate_id": saved_estimate["id"],
        "compliance_report": compliance_data,
    }

    return jsonable_encoder(response_payload)


@app.get("/estimates")
def list_estimates(admin_username: str = Depends(require_admin)):
    """
    Admin endpoint.

    Returns full estimate history from Postgres for the admin review dashboard.
    """
    estimates = get_all_estimates()
    return jsonable_encoder(estimates)

@app.post("/email/estimate-summary")
def email_estimate_summary(request: EstimateEmailRequest):
    """
    Sends a customer-safe preliminary estimate summary.

    This endpoint intentionally does not send internal estimator notes
    or the proposal draft. Those remain admin-review artifacts.
    """
    try:
        result = send_estimate_summary_email(
            to_email=request.to_email,
            customer_name=request.customer_name,
            address=request.address,
            estimate_id=request.estimate_id,
            estimated_total=request.estimated_total,
            low_range=request.low_range,
            high_range=request.high_range,
            status=request.status,
            confidence_score=request.confidence_score,
            compliance_overall=request.compliance_overall,
            compliance_jurisdiction=request.compliance_jurisdiction,
            remaining_questions=request.remaining_questions,
        )

        return result

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Could not send estimate summary email.",
                "error": str(error),
            },
        )
    
@app.patch("/estimates/{estimate_id}/admin-decision")
def save_admin_decision(
    estimate_id: int,
    request: AdminDecisionUpdateRequest,
    admin_username: str = Depends(require_admin),
):
    updated = update_admin_decision(
        estimate_id=estimate_id,
        admin_decision=request.admin_decision,
        admin_decision_notes=request.admin_decision_notes,
        admin_email_subject=request.admin_email_subject,
        admin_email_body=request.admin_email_body,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Estimate not found.")

    return jsonable_encoder(updated)


@app.post("/email/admin-approved-proposal")
def email_admin_approved_proposal(
    request: AdminProposalEmailRequest,
    admin_username: str = Depends(require_admin),
):
    try:
        result = send_admin_approved_proposal_email(
            to_email=request.to_email,
            subject=request.subject,
            body=request.body,
        )

        mark_admin_email_sent(request.estimate_id)

        return result

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Could not send admin-approved proposal email.",
                "error": str(error),
            },
        )
    
