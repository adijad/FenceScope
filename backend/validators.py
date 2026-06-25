from backend.models import EstimateRequest, RiskFlag


SITE_VISIT_RISK_TYPES = {
    "abnormal_measurement",
    "large_project",
    "pool_code_review",
    "property_line_uncertainty",
    "permit_review",
}


def determine_status(
    req: EstimateRequest,
    risk_flags: list[RiskFlag],
    missing_questions: list[str],
    confidence_score: float,
):
    if req.linear_feet <= 0:
        return "needs_estimator_review"

    site_visit_required = any(
        risk.severity == "high" or risk.risk_type in SITE_VISIT_RISK_TYPES
        for risk in risk_flags
    )

    if site_visit_required:
        return "site_visit_required"

    if confidence_score < 0.60:
        return "needs_estimator_review"

    if missing_questions:
        return "needs_customer_info"

    medium_risk_exists = any(risk.severity == "medium" for risk in risk_flags)

    if medium_risk_exists:
        return "needs_estimator_review"

    return "ready_to_send"