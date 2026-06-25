from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from compliance.agent import check_compliance
from compliance.schemas import FenceSpec, ComplianceReport

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


@app.get("/")
def root():
    return {
        "message": "FenceScope AI is running",
        "workflow": "estimate intake, map measurement, pricing, risk review, proposal generation, and human review status",
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

@app.post("/compliance/check", response_model=ComplianceReport)
def compliance_check(spec: FenceSpec):
    return check_compliance(spec)

@app.post("/estimate", response_model=EstimateResult)
def create_estimate(request: EstimateRequest):
    return run_estimate_workflow(request)