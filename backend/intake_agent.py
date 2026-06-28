# backend/intake_agent.py

import json
import os
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from backend.models import (
    IntakeAnalysisResult,
    IntakeExtractedFields,
    IntakeTextRequest,
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


load_dotenv()


ALLOWED_FENCE_TYPES = {
    "wood_privacy",
    "vinyl_privacy",
    "chain_link",
    "aluminum",
    "split_rail",
}

ALLOWED_YARD_LOCATIONS = {"front", "side", "back"}
ALLOWED_MATERIAL_GRADES = {"economy", "standard", "premium"}
ALLOWED_GATE_HARDWARE = {"standard", "self_closing", "lockable"}
ALLOWED_SLOPE_SEVERITY = {"none", "slight", "moderate", "steep"}
ALLOWED_ACCESS_LEVELS = {"easy", "limited", "difficult"}
ALLOWED_BRUSH_CLEARING = {"none", "light", "moderate", "heavy"}

BLOCKING_PROJECT_FIELDS = [
    "fence_type",
    "height_ft",
    "linear_feet",
    "yard_location",
    "gate_count",
]

DEFAULTABLE_FIELD_VALUES = {
    "material_grade": "standard",
    "gate_hardware": "standard",
    "access_level": "easy",
    "difficult_access": False,
    "brush_clearing": "none",
    "stain_seal": False,
    "permit_admin": False,
    "double_gate_count": 0,
    "old_fence_removal": False,
    "slope_present": False,
    "slope_severity": "none",
}

SYSTEM_PROMPT = """
You are FenceScope Intake Intelligence, a guardrailed intake agent for a residential fencing estimate workflow.

Your job:
1. Decide whether the user's text is related to a residential fence estimate.
2. Extract only explicitly stated or strongly supported project details.
3. Use the provided customer/address/map context when it is relevant.
4. Identify missing fields and practical follow-up questions.
5. Surface risk hints for estimator review.
6. Return only valid JSON.

Important rules:
- Do not calculate final price.
- Do not create an estimate.
- Do not invent address, contact information, dimensions, gates, material, or compliance facts.
- Do not make legal/code claims.
- Do not promise that the quote is final.
- If the text is irrelevant, unsafe, abusive, or gibberish, mark it as not relevant.
- Use null for unknown fields.
- If a map measurement is available and the user says to use the map, you may use map_linear_feet as linear_feet.
- If the user's written length conflicts with map_linear_feet, include a warning and set measurement_needs_confirmation to true.
- Convert simple length units to feet only when the user clearly provides a unit, such as meters, yards, or feet.
- If converting meters or yards to feet, store original_length_value and original_length_unit.
- Always set should_create_estimate to false.

Allowed enum values:
fence_type: wood_privacy, vinyl_privacy, chain_link, aluminum, split_rail
yard_location: front, side, back
material_grade: economy, standard, premium
gate_hardware: standard, self_closing, lockable
slope_severity: none, slight, moderate, steep
access_level: easy, limited, difficult
brush_clearing: none, light, moderate, heavy

Missing field policy:
Only include customer-facing missing_fields for details that block a useful preliminary estimate: fence_type, height_ft, linear_feet, yard_location, and gate_count. Do not ask the customer for every optional pricing add-on. Do not put default assumptions into extracted_fields unless the customer explicitly stated them. The frontend may later apply assumptions such as material_grade=standard, gate_hardware=standard, access_level=easy, brush_clearing=none, stain_seal=false, permit_admin=false, double_gate_count=0, old_fence_removal=false, slope_present=false, and slope_severity=none.

Return JSON with exactly this top-level shape:
{
  "is_relevant": true,
  "intake_category": "fence_quote_request | partial_fence_quote_request | fence_related_question | irrelevant | unsafe_or_abusive | unknown",
  "quote_readiness": "ready_for_guided_form | needs_missing_info | not_applicable | needs_human_review",
  "summary": "short summary",
  "extracted_fields": {
    "customer_name": null,
    "customer_email": null,
    "customer_phone": null,
    "address": null,
    "fence_type": null,
    "height_ft": null,
    "linear_feet": null,
    "original_length_value": null,
    "original_length_unit": null,
    "measurement_needs_confirmation": false,
    "yard_location": null,
    "gate_count": null,
    "double_gate_count": null,
    "old_fence_removal": null,
    "difficult_access": null,
    "slope_present": null,
    "material_grade": null,
    "gate_hardware": null,
    "slope_severity": null,
    "access_level": null,
    "brush_clearing": null,
    "stain_seal": null,
    "permit_admin": null,
    "project_purpose": null,
    "customer_notes": null
  },
  "missing_fields": [],
  "follow_up_questions": [],
  "risk_hints": [
    {
      "risk_type": "string",
      "severity": "low | medium | high",
      "reason": "string",
      "recommended_action": "string or null"
    }
  ],
  "warnings": [],
  "evidence": [],
  "confidence_score": 0.0,
  "user_message": "short customer-facing message",
  "should_create_estimate": false
}
"""


def _fallback_result(
    *,
    is_relevant: bool,
    category: str,
    readiness: str,
    summary: str,
    user_message: str,
    confidence_score: float = 0.0,
    missing_fields: list[str] | None = None,
    warnings: list[str] | None = None,
) -> IntakeAnalysisResult:
    return IntakeAnalysisResult(
        is_relevant=is_relevant,
        intake_category=category,
        quote_readiness=readiness,
        summary=summary,
        extracted_fields=IntakeExtractedFields(),
        missing_fields=missing_fields or [],
        follow_up_questions=[],
        risk_hints=[],
        warnings=warnings or [],
        evidence=[],
        confidence_score=confidence_score,
        user_message=user_message,
        should_create_estimate=False,
    )


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except Exception:
        return 0.0

    return max(0.0, min(1.0, number))


def _clean_enum(value: Any, allowed: set[str]):
    if value is None:
        return None

    value = str(value).strip()

    if value in allowed:
        return value

    return None


def _ensure_list(value: Any) -> list:
    if isinstance(value, list):
        return value

    if value is None:
        return []

    return [str(value)]


def _field_has_value(fields: dict[str, Any], field_name: str) -> bool:
    value = fields.get(field_name)

    if value is None:
        return False

    if value == "":
        return False

    return True


def _apply_defaultable_fields(extracted: dict[str, Any]) -> None:
    """
    Applies safe defaults for optional fields.

    These fields should usually be shown as assumptions in the customer review
    card instead of becoming customer-facing questions.
    """
    for field_name, default_value in DEFAULTABLE_FIELD_VALUES.items():
        if extracted.get(field_name) is None:
            extracted[field_name] = default_value

    access_level = extracted.get("access_level")
    if access_level in ["limited", "difficult"]:
        extracted["difficult_access"] = True
    elif access_level == "easy":
        extracted["difficult_access"] = False

    slope_severity = extracted.get("slope_severity")
    if slope_severity and slope_severity != "none":
        extracted["slope_present"] = True
    elif slope_severity == "none":
        extracted["slope_present"] = False


def _use_map_context_when_available(
    extracted: dict[str, Any],
    request: IntakeTextRequest,
) -> None:
    """
    If the user already selected/drew a map measurement, use it instead of
    asking for length again.
    """
    if not extracted.get("linear_feet") and request.map_linear_feet:
        try:
            extracted["linear_feet"] = float(request.map_linear_feet)
        except Exception:
            pass

    if extracted.get("gate_count") is None and request.gate_points:
        extracted["gate_count"] = len(request.gate_points)

    if extracted.get("double_gate_count") is None:
        extracted["double_gate_count"] = 0


def _customer_facing_missing_fields(
    model_missing_fields: list[str],
    extracted: dict[str, Any],
) -> list[str]:
    """
    Keeps only blocking fields as customer questions.

    The LLM may return optional fields as missing, but the frontend description
    path should not annoy the customer by asking every optional add-on.
    """
    missing = []

    for field_name in model_missing_fields:
        if field_name in BLOCKING_PROJECT_FIELDS and field_name not in missing:
            missing.append(field_name)

    for field_name in BLOCKING_PROJECT_FIELDS:
        if not _field_has_value(extracted, field_name) and field_name not in missing:
            missing.append(field_name)

    return missing

def _normalize_llm_payload(data: dict[str, Any], request: IntakeTextRequest) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}

    data["is_relevant"] = bool(data.get("is_relevant", False))
    data["confidence_score"] = _clamp_confidence(data.get("confidence_score", 0.0))
    data["should_create_estimate"] = False

    allowed_categories = {
        "fence_quote_request",
        "partial_fence_quote_request",
        "fence_related_question",
        "irrelevant",
        "unsafe_or_abusive",
        "unknown",
    }

    allowed_readiness = {
        "ready_for_guided_form",
        "needs_missing_info",
        "not_applicable",
        "needs_human_review",
    }

    if data.get("intake_category") not in allowed_categories:
        data["intake_category"] = "unknown"

    if data.get("quote_readiness") not in allowed_readiness:
        data["quote_readiness"] = "needs_human_review"

    data["summary"] = str(data.get("summary") or "No summary available.")
    data["user_message"] = str(
        data.get("user_message")
        or "We reviewed your description and extracted the available fence project details."
    )

    data["missing_fields"] = _ensure_list(data.get("missing_fields"))
    data["follow_up_questions"] = _ensure_list(data.get("follow_up_questions"))
    data["warnings"] = _ensure_list(data.get("warnings"))
    data["evidence"] = _ensure_list(data.get("evidence"))

    extracted = data.get("extracted_fields") or {}
    if not isinstance(extracted, dict):
        extracted = {}

    # Prefer already-collected context for customer/address fields.
    extracted["customer_name"] = request.customer_name or extracted.get("customer_name")
    extracted["customer_email"] = request.customer_email or extracted.get("customer_email")
    extracted["customer_phone"] = request.customer_phone or extracted.get("customer_phone")
    extracted["address"] = request.address or extracted.get("address")

    extracted["fence_type"] = _clean_enum(
        extracted.get("fence_type"),
        ALLOWED_FENCE_TYPES,
    )
    extracted["yard_location"] = _clean_enum(
        extracted.get("yard_location"),
        ALLOWED_YARD_LOCATIONS,
    )
    extracted["material_grade"] = _clean_enum(
        extracted.get("material_grade"),
        ALLOWED_MATERIAL_GRADES,
    )
    extracted["gate_hardware"] = _clean_enum(
        extracted.get("gate_hardware"),
        ALLOWED_GATE_HARDWARE,
    )
    extracted["slope_severity"] = _clean_enum(
        extracted.get("slope_severity"),
        ALLOWED_SLOPE_SEVERITY,
    )
    extracted["access_level"] = _clean_enum(
        extracted.get("access_level"),
        ALLOWED_ACCESS_LEVELS,
    )
    extracted["brush_clearing"] = _clean_enum(
        extracted.get("brush_clearing"),
        ALLOWED_BRUSH_CLEARING,
    )

    if extracted.get("measurement_needs_confirmation") is None:
        extracted["measurement_needs_confirmation"] = False

    data["extracted_fields"] = extracted

    if not data["is_relevant"]:
        data["quote_readiness"] = "not_applicable"
        data["missing_fields"] = []
        data["follow_up_questions"] = []
        data["risk_hints"] = []
        return data

    _use_map_context_when_available(extracted, request)

    # Do not apply optional defaults here.
    # The frontend description lane applies assumptions later and decides
    # which high-value questions to ask. This keeps extracted_fields closer
    # to what the customer actually said or what the map provided.
    data["missing_fields"] = _customer_facing_missing_fields(
        model_missing_fields=data.get("missing_fields", []),
        extracted=extracted,
    )

    data["missing_fields"] = _customer_facing_missing_fields(
        model_missing_fields=data.get("missing_fields", []),
        extracted=extracted,
    )

    # Deterministic measurement conflict guard.
    try:
        extracted_linear_feet = extracted.get("linear_feet")
        map_linear_feet = request.map_linear_feet

        if extracted_linear_feet and map_linear_feet:
            extracted_linear_feet = float(extracted_linear_feet)
            map_linear_feet = float(map_linear_feet)

            larger = max(extracted_linear_feet, map_linear_feet)
            smaller = min(extracted_linear_feet, map_linear_feet)

            if larger > 0 and (larger - smaller) / larger > 0.15:
                warning = (
                    f"Measurement conflict: description suggests {extracted_linear_feet:.1f} ft, "
                    f"but the map context is {map_linear_feet:.1f} ft."
                )

                if warning not in data["warnings"]:
                    data["warnings"].append(warning)

                extracted["measurement_needs_confirmation"] = True

                if "linear_feet" not in data["missing_fields"]:
                    data["missing_fields"].append("linear_feet")
    except Exception:
        pass

    if data["confidence_score"] < 0.45:
        data["quote_readiness"] = "needs_human_review"
    elif data["missing_fields"]:
        data["quote_readiness"] = "needs_missing_info"
    elif data["intake_category"] in ["fence_quote_request", "partial_fence_quote_request"]:
        data["quote_readiness"] = "ready_for_guided_form"

    return data


def analyze_text_intake(request: IntakeTextRequest) -> IntakeAnalysisResult:
    raw_text = request.raw_text.strip()

    if len(raw_text) < 3:
        return _fallback_result(
            is_relevant=False,
            category="unknown",
            readiness="not_applicable",
            summary="The description is too short to analyze.",
            user_message="Please provide a few details about the fence project.",
        )

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or OpenAI is None:
        return _fallback_result(
            is_relevant=False,
            category="unknown",
            readiness="needs_human_review",
            summary="The intake AI is not configured.",
            user_message=(
                "The AI intake analyzer is not configured yet. "
                "Please add OPENAI_API_KEY and try again."
            ),
            warnings=["OPENAI_API_KEY is missing or the OpenAI package is unavailable."],
        )

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    request_context = request.model_dump()

    user_prompt = {
        "task": "Analyze this unstructured fence project intake.",
        "request_context": request_context,
        "reminder": (
            "Return only valid JSON. Do not calculate price. "
            "Do not create an estimate. should_create_estimate must be false."
        ),
    }

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(user_prompt),
                },
            ],
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        normalized = _normalize_llm_payload(parsed, request)

        return IntakeAnalysisResult(**normalized)

    except (json.JSONDecodeError, ValidationError) as error:
        return _fallback_result(
            is_relevant=True,
            category="unknown",
            readiness="needs_human_review",
            summary="The AI response could not be safely parsed.",
            user_message=(
                "We could not safely structure the description. "
                "Please use the guided form or try a clearer description."
            ),
            warnings=[str(error)],
            confidence_score=0.0,
        )

    except Exception as error:
        return _fallback_result(
            is_relevant=True,
            category="unknown",
            readiness="needs_human_review",
            summary="The intake analysis failed.",
            user_message=(
                "The AI intake analyzer could not complete the review. "
                "Please use the guided form or try again."
            ),
            warnings=[str(error)],
            confidence_score=0.0,
        )