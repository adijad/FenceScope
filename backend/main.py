from fastapi import FastAPI, Query, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

from compliance.agent import check_compliance
from compliance.schemas import FenceSpec, ComplianceReport



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
)
from backend.email_service import send_estimate_summary_email
from backend.risk_agent import analyze_risks
from backend.storage import create_customer, create_estimate, get_all_estimates
from backend.workflow import run_estimate_workflow


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


def estimate_request_to_fence_spec(request: EstimateRequest) -> FenceSpec:
    material, pct_open = MATERIAL_MAP.get(request.fence_type, ("wood", 0))

    return FenceSpec(
        height_ft=request.height_ft,
        location=request.yard_location,
        material=material,
        pct_open=pct_open,
        address=request.address,
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
    spec = estimate_request_to_fence_spec(request)
    return check_compliance(spec)


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
    spec = estimate_request_to_fence_spec(request)
    compliance_report = check_compliance(spec)

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
def list_estimates():
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