"""
schemas.py
----------
Input/output contracts for the compliance agent.
(Named schemas.py, not models.py, to avoid colliding with backend/models.py.)
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field

# material is a free string; agent.normalize_material() canonicalizes variants
YardLocation = Literal["front", "side", "back"]
Verdict = Literal["PASS", "FAIL", "NEEDS_REVIEW"]
FindingStatus = Literal["pass", "fail", "needs_review"]


class FenceSpec(BaseModel):
    """What the user proposes to build."""
    height_ft: float = Field(..., gt=0, description="Proposed fence height (feet)")
    location: YardLocation
    material: str = "wood"
    corner_lot: bool = False
    pct_open: int = Field(0, ge=0, le=100, description="% open/transparent (0 = solid)")
    near_pool: bool = False
    # one of these resolves the jurisdiction:
    address: Optional[str] = None          # Google formatted address (display_name)
    jurisdiction_id: Optional[str] = None  # set directly to skip address resolution


class Finding(BaseModel):
    """One rule, evaluated against the fence."""
    rule_id: str
    status: FindingStatus
    explanation: str
    verbatim_text: Optional[str] = None    # the cited ordinance quote
    source_url: Optional[str] = None
    confidence: float = 1.0


class ComplianceReport(BaseModel):
    """What the contractor gets back."""
    matched: bool
    jurisdiction: Optional[str] = None
    jurisdiction_id: Optional[str] = None
    overall: Verdict
    findings: list[Finding] = []
    summary: str = ""
    needs_human_review: bool = False
    review_reasons: list[str] = []
    source_url: Optional[str] = None
    disclaimer: str = (
        "Informational pre-check only. Not the definitive authority. Verify with the "
        "local building/zoning department before ordering materials or building."
    )