import json
import os

from dotenv import load_dotenv

from backend.models import EstimateRequest, LineItem, RiskFlag

load_dotenv()


try:
    from openai import OpenAI
except Exception:
    OpenAI = None


SYSTEM_PROMPT = """
You are an AI assistant for a residential fencing company.

Your job is to write:
1. A professional customer-facing preliminary estimate message.
2. Internal estimator notes for the sales or estimating team.

Important rules:
- Do not invent prices.
- Do not invent measurements.
- Do not promise this is a final quote.
- Use only the structured estimate data provided.
- Be clear when customer info, estimator review, or a site visit is needed.
- Keep the customer message friendly, concise, and professional.
- Keep internal notes practical and operational.
- Return valid JSON only.
- Do not use placeholders like [Your Company Name].
- Sign off as "FenceScope AI Estimating Assistant" unless a company name is provided.
"""


def fallback_proposal(
    req: EstimateRequest,
    line_items: list[LineItem],
    estimated_total: float,
    low_range: float,
    high_range: float,
    risk_flags: list[RiskFlag],
    missing_questions: list[str],
    status: str,
):
    questions_text = "\n".join([f"- {q}" for q in missing_questions]) or "- No missing questions."

    risks_text = "\n".join(
        [
            f"- {risk.risk_type} ({risk.severity}): {risk.explanation}"
            for risk in risk_flags
        ]
    ) or "- No major risks flagged."

    customer_proposal = f"""
Hi {req.customer_name},

Thanks for reaching out. Based on the information provided, we prepared a preliminary estimate for your {req.height_ft}-foot {req.fence_type.replace("_", " ")} fence at {req.address}.

Estimated fence length: {req.linear_feet} linear feet
Preliminary estimate: ${estimated_total:,.2f}
Expected range: ${low_range:,.2f} to ${high_range:,.2f}

Before this can be treated as a final quote, we may need to confirm a few details:

{questions_text}

Current estimate status: {status.replace("_", " ").title()}

Best,
FenceScope AI Estimating Assistant
""".strip()

    internal_notes = f"""
Estimate status: {status}
Customer: {req.customer_name}
Address: {req.address}
Fence type: {req.fence_type}
Height: {req.height_ft} ft
Measured length: {req.linear_feet} linear feet
Estimated total: ${estimated_total:,.2f}
Expected range: ${low_range:,.2f} to ${high_range:,.2f}

Risk flags:
{risks_text}

Missing questions:
{questions_text}
""".strip()

    return customer_proposal, internal_notes


def draft_proposal(
    req: EstimateRequest,
    line_items: list[LineItem],
    estimated_total: float,
    low_range: float,
    high_range: float,
    risk_flags: list[RiskFlag],
    missing_questions: list[str],
    status: str,
):
    api_key = os.getenv("OPENAI_API_KEY")

    if OpenAI is None or not api_key:
        return fallback_proposal(
            req,
            line_items,
            estimated_total,
            low_range,
            high_range,
            risk_flags,
            missing_questions,
            status,
        )

    try:
        client = OpenAI(api_key=api_key)

        payload = {
            "customer": {
                "name": req.customer_name,
                "address": req.address,
                "notes": req.customer_notes,
            },
            "job": {
                "fence_type": req.fence_type,
                "height_ft": req.height_ft,
                "linear_feet": req.linear_feet,
                "gate_count": req.gate_count,
                "double_gate_count": req.double_gate_count,
                "old_fence_removal": req.old_fence_removal,
                "difficult_access": req.difficult_access,
                "slope_present": req.slope_present,
            },
            "pricing": {
                "estimated_total": estimated_total,
                "low_range": low_range,
                "high_range": high_range,
                "line_items": [item.model_dump() for item in line_items],
            },
            "review": {
                "status": status,
                "risk_flags": [risk.model_dump() for risk in risk_flags],
                "missing_questions": missing_questions,
            },
        }

        user_prompt = f"""
Write a customer proposal and internal estimator notes for this fence estimate.

Structured estimate data:
{json.dumps(payload, indent=2)}

Return JSON in this exact shape:

{{
  "customer_proposal": "customer-facing message",
  "internal_notes": "internal estimator notes"
}}
"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw_content = response.choices[0].message.content
        data = json.loads(raw_content)

        return data["customer_proposal"], data["internal_notes"]

    except Exception as error:
        print(f"LLM proposal generation failed. Falling back to template. Error: {error}")

        return fallback_proposal(
            req,
            line_items,
            estimated_total,
            low_range,
            high_range,
            risk_flags,
            missing_questions,
            status,
        )