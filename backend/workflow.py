from backend.models import EstimateRequest, EstimateResult
from backend.pricing import calculate_price
from backend.risk_agent import analyze_risks
from backend.validators import determine_status
from backend.proposal_agent import draft_proposal


def run_estimate_workflow(req: EstimateRequest) -> EstimateResult:
    # 1. Deterministic pricing
    line_items, subtotal, estimated_total, low_range, high_range = calculate_price(req)

    # 2. Hybrid risk analysis: rules + LLM
    risk_flags, missing_questions, confidence_score = analyze_risks(req)

    # 3. Deterministic business status
    status = determine_status(
        req=req,
        risk_flags=risk_flags,
        missing_questions=missing_questions,
        confidence_score=confidence_score,
    )

    # 4. LLM proposal generation with fallback template
    customer_proposal, internal_notes = draft_proposal(
        req=req,
        line_items=line_items,
        estimated_total=estimated_total,
        low_range=low_range,
        high_range=high_range,
        risk_flags=risk_flags,
        missing_questions=missing_questions,
        status=status,
    )

    # 5. Final structured result
    return EstimateResult(
        customer_name=req.customer_name,
        address=req.address,
        total_feet=req.linear_feet,
        line_items=line_items,
        subtotal=subtotal,
        estimated_total=estimated_total,
        low_range=low_range,
        high_range=high_range,
        risk_flags=risk_flags,
        missing_questions=missing_questions,
        confidence_score=confidence_score,
        status=status,
        customer_proposal=customer_proposal,
        internal_notes=internal_notes,
    )