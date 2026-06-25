import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from backend.models import EstimateRequest, RiskFlag

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


SYSTEM_PROMPT = """
You are an AI estimating assistant for a residential fencing company.

Your job is to review customer-provided job details and identify project risks,
missing questions, and next-step recommendations.

You do NOT calculate price.
You do NOT invent facts.
You only use the information provided by the customer and estimator.

Focus on risks that matter for residential fence estimating:
- HOA approval
- permit/code issues
- pool fencing
- property line uncertainty
- old fence removal
- slope or grade change
- difficult access
- trees, brush, roots, rocks, or obstructions
- dogs or pet containment
- neighbor/shared fence issues
- timeline urgency
- gate ambiguity
- material ambiguity
- site visit needed

Return valid JSON only.
"""


def analyze_risks_with_llm(req: EstimateRequest) -> tuple[list[RiskFlag], list[str], float]:
    user_prompt = f"""
Review this residential fence estimate request.

Customer name: {req.customer_name}
Address: {req.address}
Fence type: {req.fence_type}
Fence height: {req.height_ft}
Linear feet: {req.linear_feet}
Walk gates: {req.gate_count}
Double gates: {req.double_gate_count}
Old fence removal selected: {req.old_fence_removal}
Difficult access selected: {req.difficult_access}
Slope selected: {req.slope_present}
Customer notes: {req.customer_notes or "No customer notes provided."}

Return JSON in this exact shape:

{{
  "risk_flags": [
    {{
      "risk_type": "short_snake_case_name",
      "severity": "low | medium | high",
      "explanation": "brief explanation",
      "recommended_action": "what the estimator should do next"
    }}
  ],
  "missing_questions": [
    "question to ask the customer"
  ],
  "confidence_score": 0.0
}}

Rules:
- confidence_score should be between 0 and 1.
- Use high severity only when a final quote should not be sent without review.
- Use medium severity when the estimate can be prepared but needs clarification.
- Use low severity for minor sales or installation considerations.
- Do not include duplicate questions.
- Do not calculate price.
- Do not claim anything that was not stated or strongly implied.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content
    data: dict[str, Any] = json.loads(raw_content)

    risk_flags = [
        RiskFlag(
            risk_type=item["risk_type"],
            severity=item["severity"],
            explanation=item["explanation"],
            recommended_action=item["recommended_action"],
        )
        for item in data.get("risk_flags", [])
    ]

    missing_questions = data.get("missing_questions", [])
    confidence_score = float(data.get("confidence_score", 0.75))

    confidence_score = max(0.0, min(1.0, round(confidence_score, 2)))

    return risk_flags, missing_questions, confidence_score