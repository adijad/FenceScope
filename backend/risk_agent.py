from backend.models import EstimateRequest, RiskFlag

try:
    from backend.llm_risk_agent import analyze_risks_with_llm
except Exception:
    analyze_risks_with_llm = None


def analyze_rule_based_risks(req: EstimateRequest):
    risks: list[RiskFlag] = []
    missing_questions: list[str] = []

    notes = (req.customer_notes or "").lower()

    if req.linear_feet <= 20:
        risks.append(
            RiskFlag(
                risk_type="abnormal_measurement",
                severity="high",
                explanation="The measured fence length is unusually short for a residential fence project.",
                recommended_action="Confirm the fence layout before sending the estimate.",
            )
        )

    if req.linear_feet >= 700:
        risks.append(
            RiskFlag(
                risk_type="large_project",
                severity="high",
                explanation="The measured fence length is unusually large for a typical residential fence project.",
                recommended_action="Require estimator review or a site visit before sending a final quote.",
            )
        )

    if req.old_fence_removal:
        risks.append(
            RiskFlag(
                risk_type="old_fence_removal",
                severity="medium",
                explanation="Removing an existing fence can change labor time, disposal cost, and job complexity.",
                recommended_action="Confirm the material, condition, and accessibility of the existing fence.",
            )
        )
        missing_questions.append(
            "What material is the existing fence, and is it already damaged or partially removed?"
        )

    if req.slope_present or "slope" in notes or "sloped" in notes or "hill" in notes:
        risks.append(
            RiskFlag(
                risk_type="slope_or_grade_change",
                severity="medium",
                explanation="Slope or grade changes can affect installation difficulty, panel layout, and labor time.",
                recommended_action="Have the estimator review photos or verify the slope during a site visit.",
            )
        )

    if req.difficult_access or "tight access" in notes or "limited access" in notes:
        risks.append(
            RiskFlag(
                risk_type="difficult_access",
                severity="medium",
                explanation="Limited access can slow down material movement and installation.",
                recommended_action="Confirm whether crews can access the backyard with tools, posts, and panels.",
            )
        )
        missing_questions.append(
            "Is there clear access to the installation area for materials and crew equipment?"
        )

    if "hoa" in notes or "homeowners association" in notes:
        risks.append(
            RiskFlag(
                risk_type="hoa_approval",
                severity="medium",
                explanation="The customer mentioned an HOA, which may require approval for fence type, height, and color.",
                recommended_action="Ask whether HOA approval has already been obtained before scheduling installation.",
            )
        )
        missing_questions.append(
            "Has HOA approval already been obtained for this fence type, height, and color?"
        )

    if "pool" in notes or "swimming" in notes:
        risks.append(
            RiskFlag(
                risk_type="pool_code_review",
                severity="high",
                explanation="Fence projects around pools may involve local safety code requirements.",
                recommended_action="Require estimator review before sending a final quote.",
            )
        )
        missing_questions.append(
            "Is this fence intended to enclose a pool or meet pool safety code requirements?"
        )

    if "permit" in notes:
        risks.append(
            RiskFlag(
                risk_type="permit_review",
                severity="medium",
                explanation="The customer mentioned permits, which may affect timeline and approval requirements.",
                recommended_action="Confirm whether the customer or company is responsible for permit handling.",
            )
        )
        missing_questions.append(
            "Is a permit required for this fence, and who will be responsible for obtaining it?"
        )

    obstruction_keywords = ["tree", "trees", "brush", "bush", "bushes", "overgrown", "roots"]

    if any(keyword in notes for keyword in obstruction_keywords):
        risks.append(
            RiskFlag(
                risk_type="yard_obstruction",
                severity="medium",
                explanation="Trees, brush, roots, or overgrown areas can affect installation difficulty.",
                recommended_action="Ask for photos or schedule a site review before finalizing the quote.",
            )
        )
        missing_questions.append(
            "Are there trees, brush, roots, or other obstructions along the planned fence line?"
        )

    if "dog" in notes or "pet" in notes or "pets" in notes:
        risks.append(
            RiskFlag(
                risk_type="pet_containment",
                severity="low",
                explanation="The customer mentioned pets, so gate placement and ground gaps may matter.",
                recommended_action="Confirm whether the fence is intended for pet containment.",
            )
        )
        missing_questions.append(
            "Is the fence mainly intended to contain pets, and are there any gap or gate concerns?"
        )

    if req.gate_count == 0 and req.double_gate_count == 0:
        missing_questions.append("Does the customer need any walk gates or double gates?")

    if req.gate_count + req.double_gate_count >= 4:
        risks.append(
            RiskFlag(
                risk_type="many_gates",
                severity="medium",
                explanation="The project includes several gates, which can materially affect cost and layout.",
                recommended_action="Confirm gate count, gate width, and gate locations before final quote.",
            )
        )

    if "asap" in notes or "quickly" in notes or "urgent" in notes or "soon" in notes:
        risks.append(
            RiskFlag(
                risk_type="timeline_pressure",
                severity="low",
                explanation="The customer appears to want the project completed quickly.",
                recommended_action="Confirm desired installation timeline and crew availability.",
            )
        )
        missing_questions.append("What is the customer's desired installation timeline?")

    confidence_score = calculate_confidence_score(risks, missing_questions)

    return risks, missing_questions, confidence_score


def calculate_confidence_score(risks: list[RiskFlag], missing_questions: list[str]) -> float:
    confidence_score = 0.95

    for risk in risks:
        if risk.severity == "high":
            confidence_score -= 0.20
        elif risk.severity == "medium":
            confidence_score -= 0.10
        else:
            confidence_score -= 0.04

    confidence_score -= 0.03 * len(missing_questions)

    return max(0.35, min(1.0, round(confidence_score, 2)))


def normalize_risk_type(risk_type: str) -> str:
    risk_type = risk_type.strip().lower()

    aliases = {
        "timeline_urgency": "timeline_pressure",
        "urgent_timeline": "timeline_pressure",
        "quick_quote": "timeline_pressure",
        "schedule_urgency": "timeline_pressure",

        "hoa": "hoa_approval",
        "hoa_required": "hoa_approval",
        "homeowners_association": "hoa_approval",

        "slope": "slope_or_grade_change",
        "grade_change": "slope_or_grade_change",
        "sloped_yard": "slope_or_grade_change",

        "pet": "pet_containment",
        "dogs": "pet_containment",
        "dog_containment": "pet_containment",

        "fence_removal": "old_fence_removal",
        "existing_fence_removal": "old_fence_removal",

        "pool": "pool_code_review",
        "pool_code": "pool_code_review",
    }

    return aliases.get(risk_type, risk_type)


def merge_risk_flags(rule_risks: list[RiskFlag], llm_risks: list[RiskFlag]) -> list[RiskFlag]:
    merged_by_type: dict[str, RiskFlag] = {}

    severity_rank = {
        "low": 1,
        "medium": 2,
        "high": 3,
    }

    for risk in rule_risks + llm_risks:
        normalized_type = normalize_risk_type(risk.risk_type)

        normalized_risk = RiskFlag(
            risk_type=normalized_type,
            severity=risk.severity,
            explanation=risk.explanation,
            recommended_action=risk.recommended_action,
        )

        if normalized_type not in merged_by_type:
            merged_by_type[normalized_type] = normalized_risk
            continue

        existing = merged_by_type[normalized_type]

        if severity_rank[normalized_risk.severity] > severity_rank[existing.severity]:
            merged_by_type[normalized_type] = normalized_risk

    return list(merged_by_type.values())


def normalize_question(question: str) -> str:
    q = question.strip().lower()

    replacements = [
        ("has hoa approval already been obtained for this fence type, height, and color?", "hoa_approval"),
        ("has hoa approval been obtained for the fence installation?", "hoa_approval"),
        ("what is the customer's desired installation timeline?", "timeline"),
        ("what is your desired timeline for installation after receiving the quote?", "timeline"),
        ("is the fence mainly intended to contain pets, and are there any gap or gate concerns?", "pet_containment"),
        ("are there any specific pet containment requirements for your dogs?", "pet_containment"),
        ("what material is the existing fence, and is it already damaged or partially removed?", "old_fence_removal"),
        ("do you require disposal of the old fence materials or will you handle it?", "old_fence_disposal"),
    ]

    for text, key in replacements:
        if q == text:
            return key

    if "hoa" in q:
        return "hoa_approval"

    if "timeline" in q or "installation" in q:
        return "timeline"

    if "pet" in q or "dog" in q:
        return "pet_containment"

    if "old fence" in q or "existing fence" in q:
        return "old_fence_removal"

    if "slope" in q or "grade" in q:
        return "slope"

    return q


def merge_questions(rule_questions: list[str], llm_questions: list[str]) -> list[str]:
    merged: list[str] = []
    seen_keys = set()

    for question in rule_questions + llm_questions:
        key = normalize_question(question)

        if key and key not in seen_keys:
            merged.append(question)
            seen_keys.add(key)

    return merged


def analyze_risks(req: EstimateRequest):
    rule_risks, rule_questions, rule_confidence = analyze_rule_based_risks(req)

    llm_risks: list[RiskFlag] = []
    llm_questions: list[str] = []
    llm_confidence = rule_confidence

    if analyze_risks_with_llm is not None:
        try:
            llm_risks, llm_questions, llm_confidence = analyze_risks_with_llm(req)
        except Exception as error:
            print(f"LLM risk analysis failed. Falling back to rule-based risks. Error: {error}")

    final_risks = merge_risk_flags(rule_risks, llm_risks)
    final_questions = merge_questions(rule_questions, llm_questions)

    final_confidence = calculate_confidence_score(final_risks, final_questions)

    if llm_confidence is not None:
        final_confidence = min(final_confidence, llm_confidence)

    final_confidence = max(0.35, min(1.0, round(final_confidence, 2)))

    answered_questions = {
    question.strip().lower()
    for question, answer in (req.missing_answers or {}).items()
    if answer and answer.strip()
    }

    final_questions = [
        question
        for question in final_questions
        if question.strip().lower() not in answered_questions
]

    return final_risks, final_questions, final_confidence