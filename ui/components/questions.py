# ui/components/questions.py

import re

import streamlit as st


def normalize_question_text(question: str) -> str:
    return question.strip().lower()


def question_key_from_text(question: str) -> str:
    q = normalize_question_text(question)

    if "hoa" in q:
        return "hoa_approval"

    if "pet" in q or "dog" in q:
        return "pet_containment"

    if "timeline" in q or "desired installation" in q or "schedule" in q:
        return "timeline"

    if "material" in q and ("existing fence" in q or "old fence" in q):
        return "existing_fence_material"

    if "condition" in q and ("old" in q or "existing" in q or "chain link" in q):
        return "old_fence_condition_length"

    if "slope" in q or "grade" in q:
        return "slope_details"

    if "property line" in q or "neighbor" in q or "shared fence" in q:
        return "property_line_uncertainty"

    if "access" in q:
        return "access_details"

    if "gate" in q:
        return "gate_details"

    return "free_text"


def stable_question_suffix(question: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", question.strip().lower())
    return cleaned[:50]


def render_typed_question_input(question: str, idx: int) -> str:
    question_key = question_key_from_text(question)
    question_suffix = stable_question_suffix(question)
    base_key = f"typed_question_{idx}_{question_key}_{question_suffix}"

    st.markdown(f"**{question}**")

    if question_key == "hoa_approval":
        answer = st.selectbox(
            "HOA approval status",
            [
                "Select an option",
                "Yes, HOA approval has been obtained",
                "No, HOA approval has not been obtained",
                "Not sure / customer needs to check",
                "No HOA applies to this property",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "pet_containment":
        primary = st.selectbox(
            "Is this fence intended for pet containment?",
            [
                "Select an option",
                "Yes, mainly for pet containment",
                "Partially, pets are one reason",
                "No, not for pet containment",
            ],
            key=f"{base_key}_select",
        )

        details = st.text_input(
            "Optional pet details",
            placeholder="Example: two dogs, small dog gap concerns, gate latch concerns",
            key=f"{base_key}_details",
        )

        if primary == "Select an option":
            return ""

        if details.strip():
            return f"{primary}. Details: {details.strip()}"

        return primary

    if question_key == "timeline":
        answer = st.selectbox(
            "Desired installation timeline",
            [
                "Select an option",
                "ASAP",
                "Within 1 to 2 weeks",
                "Within 2 to 4 weeks",
                "Within 1 to 2 months",
                "Flexible / no rush",
                "Customer is not sure yet",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "existing_fence_material":
        material = st.selectbox(
            "Existing fence material",
            [
                "Select an option",
                "Chain link",
                "Wood",
                "Vinyl",
                "Aluminum",
                "Split rail",
                "Mixed materials",
                "Not sure",
                "No existing fence",
            ],
            key=f"{base_key}_material",
        )

        condition = st.selectbox(
            "Existing fence condition",
            [
                "Select an option",
                "Good condition",
                "Partially damaged",
                "Heavily damaged",
                "Partially removed already",
                "Fully standing",
                "Not sure",
                "Not applicable",
            ],
            key=f"{base_key}_condition",
        )

        if material == "Select an option" or condition == "Select an option":
            return ""

        return f"Existing fence material: {material}. Condition: {condition}."

    if question_key == "old_fence_condition_length":
        condition = st.selectbox(
            "Old fence condition",
            [
                "Select an option",
                "Good condition",
                "Partially damaged",
                "Heavily damaged",
                "Partially removed already",
                "Fully standing",
                "Not sure",
            ],
            key=f"{base_key}_condition",
        )

        old_fence_length = st.number_input(
            "Approximate old fence length to remove",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"{base_key}_length",
        )

        if condition == "Select an option":
            return ""

        if old_fence_length <= 0:
            return f"Old fence condition: {condition}. Old fence length: not sure."

        return (
            f"Old fence condition: {condition}. "
            f"Approximate removal length: {old_fence_length:.0f} linear feet."
        )

    if question_key == "slope_details":
        slope_level = st.selectbox(
            "Slope severity",
            [
                "Select an option",
                "Slight slope",
                "Moderate slope",
                "Steep slope",
                "Mixed slope across yard",
                "Not sure",
            ],
            key=f"{base_key}_slope_level",
        )

        slope_uniformity = st.selectbox(
            "Slope pattern",
            [
                "Select an option",
                "Mostly uniform",
                "Varies across the fence line",
                "Only one section is sloped",
                "Not sure",
            ],
            key=f"{base_key}_slope_pattern",
        )

        details = st.text_input(
            "Optional slope details",
            placeholder="Example: backyard slopes down toward the street",
            key=f"{base_key}_details",
        )

        if slope_level == "Select an option" or slope_uniformity == "Select an option":
            return ""

        answer = f"Slope severity: {slope_level}. Slope pattern: {slope_uniformity}."

        if details.strip():
            answer += f" Details: {details.strip()}"

        return answer

    if question_key == "property_line_uncertainty":
        answer = st.selectbox(
            "Property line or neighbor uncertainty",
            [
                "Select an option",
                "No known property line uncertainty",
                "Customer is not sure about property line",
                "Fence may be shared with neighbor",
                "Survey may be needed",
                "Neighbor approval may be needed",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "access_details":
        answer = st.selectbox(
            "Crew access to fence area",
            [
                "Select an option",
                "Clear access",
                "Narrow gate access",
                "No vehicle access",
                "Steep or difficult access",
                "Obstructions may need removal",
                "Not sure",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "gate_details":
        answer = st.text_input(
            "Gate details",
            placeholder="Example: one 4 ft walk gate on left side, one double gate near driveway",
            key=f"{base_key}_text",
        )

        return answer.strip()

    answer = st.text_input(
        "Answer",
        key=f"{base_key}_text",
    )

    return answer.strip()