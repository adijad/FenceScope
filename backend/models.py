from pydantic import BaseModel
from typing import List, Optional, Literal


FenceType = Literal[
    "wood_privacy",
    "vinyl_privacy",
    "chain_link",
    "aluminum",
    "split_rail",
]


EstimateStatus = Literal[
    "ready_to_send",
    "needs_customer_info",
    "needs_estimator_review",
    "site_visit_required",
]


class EstimateRequest(BaseModel):
    customer_name: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None

    address: str
    property_lat: Optional[float] = None
    property_lng: Optional[float] = None

    fence_type: FenceType
    height_ft: int = 6
    linear_feet: float
    gate_count: int = 0
    double_gate_count: int = 0
    old_fence_removal: bool = False
    difficult_access: bool = False
    slope_present: bool = False
    customer_notes: Optional[str] = None


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