from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from compliance.agent import check_compliance
from compliance.schemas import FenceSpec, ComplianceReport

from backend.models import EstimateRequest, EstimateResult, MissingQuestionsResult
from backend.risk_agent import analyze_risks

from backend.address_lookup import (
    autocomplete_address,
    get_place_details,
    search_address,
)
from backend.models import EstimateRequest, EstimateResult
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
            "estimate intake, map measurement, compliance pre-check, pricing, "
            "risk review, proposal generation, and human review status"
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


@app.post("/estimate", response_model=EstimateResult)
def create_estimate(request: EstimateRequest):
    """
    Final estimate endpoint.

    Important:
    This endpoint also runs compliance as a backend guard. The frontend should
    call /precheck first, but the backend must still protect the workflow.
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

    return run_estimate_workflow(request)