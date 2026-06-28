from pydantic import BaseModel, Field
from typing import List, Optional, Literal


FenceType = Literal[
    "wood_privacy",
    "vinyl_privacy",
    "chain_link",
    "aluminum",
    "split_rail",
]

YardLocation = Literal["front", "side", "back"]

EstimateStatus = Literal[
    "ready_to_send",
    "needs_customer_info",
    "needs_estimator_review",
    "site_visit_required",
]


AdminDecision = Literal[
    "under_review",
    "approved_to_send",
    "needs_customer_info",
    "needs_site_visit",
    "cannot_quote_as_entered",
]

MaterialGrade = Literal["economy", "standard", "premium"]
GateHardware = Literal["standard", "self_closing", "lockable"]
SlopeSeverity = Literal["none", "slight", "moderate", "steep"]
AccessLevel = Literal["easy", "limited", "difficult"]
BrushClearing = Literal["none", "light", "moderate", "heavy"]

class YardSection(BaseModel):
    location: YardLocation
    included: bool = True
    height_ft: int = 6
    linear_feet: Optional[float] = None


class EstimateRequest(BaseModel):
    customer_name: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None

    address: str
    property_lat: Optional[float] = None
    property_lng: Optional[float] = None

    # Backward-compatible primary location.
    yard_location: YardLocation = "back"

    # Optional richer section breakdown.
    yard_sections: Optional[List[YardSection]] = None

    fence_type: FenceType
    height_ft: int = 6
    linear_feet: float
    gate_count: int = 0
    double_gate_count: int = 0
    old_fence_removal: bool = False
    difficult_access: bool = False
    slope_present: bool = False
    customer_notes: Optional[str] = None

    # Pricing v2 inputs.
    material_grade: MaterialGrade = "standard"
    gate_hardware: GateHardware = "standard"
    removal_length_feet: Optional[float] = None
    slope_severity: SlopeSeverity = "none"
    access_level: AccessLevel = "easy"
    brush_clearing: BrushClearing = "none"
    stain_seal: bool = False
    permit_admin: bool = False

    missing_answers: Optional[dict[str, str]] = None


class LineItem(BaseModel):
    label: str
    quantity: float
    unit: str
    unit_cost: float
    total: float


class RiskFlag(BaseModel):
    risk_type: str
    severity: Literal["low", "medium", "high"]
    explanation: str
    recommended_action: str


class MissingQuestionsResult(BaseModel):
    risk_flags: List[RiskFlag]
    missing_questions: List[str]
    confidence_score: float

class AdminDecisionUpdateRequest(BaseModel):
    admin_decision: AdminDecision
    admin_decision_notes: Optional[str] = None
    admin_email_subject: Optional[str] = None
    admin_email_body: Optional[str] = None


class AdminProposalEmailRequest(BaseModel):
    estimate_id: int
    to_email: str
    subject: str
    body: str

class EstimateResult(BaseModel):
    customer_name: str
    address: str
    total_feet: float
    line_items: List[LineItem]
    subtotal: float
    estimated_total: float
    low_range: float
    high_range: float
    risk_flags: List[RiskFlag]
    missing_questions: List[str]
    confidence_score: float
    status: EstimateStatus
    customer_proposal: str
    internal_notes: str


class EstimateEmailRequest(BaseModel):
    to_email: str
    customer_name: str
    address: str
    estimate_id: Optional[int] = None
    estimated_total: float
    low_range: float
    high_range: float
    status: str
    confidence_score: float
    compliance_overall: Optional[str] = None
    compliance_jurisdiction: Optional[str] = None
    remaining_questions: List[str] = Field(default_factory=list)


# ---------------------------------------------------------
# Unstructured intake models
# ---------------------------------------------------------

IntakeCategory = Literal[
    "fence_quote_request",
    "partial_fence_quote_request",
    "fence_related_question",
    "irrelevant",
    "unsafe_or_abusive",
    "unknown",
]

QuoteReadiness = Literal[
    "ready_for_guided_form",
    "needs_missing_info",
    "not_applicable",
    "needs_human_review",
]


class IntakeGatePoint(BaseModel):
    lat: float
    lng: float


class IntakeTextRequest(BaseModel):
    raw_text: str = Field(..., min_length=3, max_length=6000)

    # Context already collected by the app.
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    address: Optional[str] = None
    property_lat: Optional[float] = None
    property_lng: Optional[float] = None

    # Optional map context.
    map_linear_feet: Optional[float] = None
    drawn_feet: Optional[float] = None
    use_map_measurement: Optional[bool] = None
    gate_points: List[IntakeGatePoint] = Field(default_factory=list)


class IntakeRiskHint(BaseModel):
    risk_type: str
    severity: Literal["low", "medium", "high"]
    reason: str
    recommended_action: Optional[str] = None


class IntakeExtractedFields(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    address: Optional[str] = None

    fence_type: Optional[FenceType] = None
    height_ft: Optional[int] = Field(default=None, ge=3, le=10)
    linear_feet: Optional[float] = Field(default=None, gt=0)

    original_length_value: Optional[float] = None
    original_length_unit: Optional[str] = None
    measurement_needs_confirmation: bool = False

    yard_location: Optional[YardLocation] = None
    gate_count: Optional[int] = Field(default=None, ge=0)
    double_gate_count: Optional[int] = Field(default=None, ge=0)

    old_fence_removal: Optional[bool] = None
    difficult_access: Optional[bool] = None
    slope_present: Optional[bool] = None

    material_grade: Optional[MaterialGrade] = None
    gate_hardware: Optional[GateHardware] = None
    slope_severity: Optional[SlopeSeverity] = None
    access_level: Optional[AccessLevel] = None
    brush_clearing: Optional[BrushClearing] = None
    stain_seal: Optional[bool] = None
    permit_admin: Optional[bool] = None

    project_purpose: Optional[str] = None
    customer_notes: Optional[str] = None


class IntakeAnalysisResult(BaseModel):
    is_relevant: bool
    intake_category: IntakeCategory
    quote_readiness: QuoteReadiness

    summary: str
    extracted_fields: IntakeExtractedFields = Field(default_factory=IntakeExtractedFields)

    missing_fields: List[str] = Field(default_factory=list)
    follow_up_questions: List[str] = Field(default_factory=list)
    risk_hints: List[IntakeRiskHint] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)

    confidence_score: float = Field(0.0, ge=0.0, le=1.0)

    user_message: str

    # This must remain false. The LLM intake agent is not allowed to create
    # estimates directly. The user must review/complete details first.
    should_create_estimate: bool = False