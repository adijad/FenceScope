# ui/components/description_intake.py

import requests
import streamlit as st

from ui.api_client import analyze_text_intake_request
from ui.components.intake_choice import GUIDED_FORM_MODE
from ui.formatting import fence_type_label, status_label, yard_location_label
from ui.state import (
    reset_description_intake_state,
    reset_guided_review_state,
)
from ui.workflows.guided_review import render_guided_estimate_workflow


BLOCKING_FIELDS = [
    "fence_type",
    "height_ft",
    "linear_feet",
    "yard_location",
    "gate_count",
]

CONFIRMATION_FIELDS = [
    "linear_feet",
    "material_grade",
    "access_level",
    "brush_clearing",
]

MAX_DESCRIPTION_QUESTIONS = 5

DEFAULT_FIELD_VALUES = {
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

FIELD_QUESTION_TEXT = {
    "linear_feet": "What total fence length should we use?",
    "fence_type": "What type of fence do you want?",
    "height_ft": "What fence height do you want?",
    "yard_location": "Which yard area is this fence mainly for?",
    "gate_count": "How many walk gates do you need?",
    "material_grade": "What material grade do you prefer?",
    "access_level": "How easy is it for the crew to access the fence area?",
    "brush_clearing": "Will any brush or obstruction clearing be needed?",
}


def build_description_context_preview(customer_property_context: dict) -> dict:
    map_context = customer_property_context.get("map_context", {}) or {}

    return {
        "customer_name": customer_property_context.get("customer_name"),
        "customer_email": customer_property_context.get("customer_email"),
        "customer_phone": customer_property_context.get("customer_phone"),
        "address": customer_property_context.get("selected_address"),
        "property_lat": customer_property_context.get("property_lat"),
        "property_lng": customer_property_context.get("property_lng"),
        "map_linear_feet": map_context.get("final_linear_feet"),
        "drawn_feet": map_context.get("drawn_feet"),
        "use_map_measurement": map_context.get("use_map_measurement"),
        "gate_points": map_context.get("gate_points", []),
    }


def build_intake_request_payload(
    customer_property_context: dict,
    raw_description: str,
) -> dict:
    map_context = customer_property_context.get("map_context", {}) or {}

    return {
        "raw_text": raw_description,
        "customer_name": customer_property_context.get("customer_name"),
        "customer_email": customer_property_context.get("customer_email"),
        "customer_phone": customer_property_context.get("customer_phone"),
        "address": customer_property_context.get("selected_address"),
        "property_lat": customer_property_context.get("property_lat"),
        "property_lng": customer_property_context.get("property_lng"),
        "map_linear_feet": map_context.get("final_linear_feet"),
        "drawn_feet": map_context.get("drawn_feet"),
        "use_map_measurement": map_context.get("use_map_measurement"),
        "gate_points": map_context.get("gate_points", []),
    }


def render_description_context(customer_property_context: dict):
    context_preview = build_description_context_preview(customer_property_context)

    with st.container(border=True):
        st.markdown("### Property context")
        st.write(f"**Customer:** {context_preview.get('customer_name') or 'Missing'}")
        st.write(f"**Address:** {context_preview.get('address') or 'Missing'}")

        map_linear_feet = context_preview.get("map_linear_feet")
        drawn_feet = context_preview.get("drawn_feet")
        gate_markers = len(context_preview.get("gate_points", []))

        if drawn_feet:
            st.write(f"**Map measurement:** {float(drawn_feet):,.2f} ft")
        elif map_linear_feet:
            st.write(f"**Fallback length:** {float(map_linear_feet):,.2f} ft")
        else:
            st.write("**Fence length:** Not provided yet")

        st.write(f"**Gate markers:** {gate_markers}")


def render_description_guidance():
    with st.expander("What should I include?", expanded=False):
        st.markdown(
            """
            Helpful details include fence type, height, approximate length, yard location,
            gates, old fence removal, slope, access, pets, pool, HOA, property-line concerns,
            and timeline.
            """
        )


def render_description_text_area() -> str:
    raw_description = st.text_area(
        "Describe your fence project",
        value=st.session_state.get("raw_project_description", ""),
        height=220,
        placeholder=(
            "Example: I want a 6 ft wood privacy fence around my backyard. "
            "We have two dogs, need one walk gate near the driveway, and there is an old "
            "chain link fence that may need to be removed. The backyard has a slight slope."
        ),
        key="description_intake_text_area",
    )

    st.session_state.raw_project_description = raw_description

    return raw_description


def _has_value(value) -> bool:
    if value is None:
        return False

    if value == "":
        return False

    return True


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_bool(value, default=False):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in ["true", "yes", "1"]

    return bool(value)


def _clean_extracted_fields(analysis: dict) -> dict:
    extracted = analysis.get("extracted_fields", {}) or {}

    cleaned = {}

    for key, value in extracted.items():
        if value is None:
            continue

        if value == "":
            continue

        cleaned[key] = value

    return cleaned


def _apply_defaults_and_context(fields: dict, customer_property_context: dict) -> dict:
    final_fields = DEFAULT_FIELD_VALUES.copy()
    final_fields.update(fields)

    map_context = customer_property_context.get("map_context", {}) or {}
    map_linear_feet = map_context.get("final_linear_feet")
    gate_points = map_context.get("gate_points", [])

    if not _has_value(final_fields.get("linear_feet")) and map_linear_feet:
        final_fields["linear_feet"] = float(map_linear_feet)

    if not _has_value(final_fields.get("gate_count")) and gate_points:
        final_fields["gate_count"] = len(gate_points)

    if not _has_value(final_fields.get("double_gate_count")):
        final_fields["double_gate_count"] = 0

    access_level = final_fields.get("access_level")
    if access_level in ["limited", "difficult"]:
        final_fields["difficult_access"] = True
    elif access_level == "easy":
        final_fields["difficult_access"] = False

    slope_severity = final_fields.get("slope_severity")
    if slope_severity and slope_severity != "none":
        final_fields["slope_present"] = True
    elif slope_severity == "none":
        final_fields["slope_present"] = False

    return final_fields


def _add_question(question_items: list[dict], seen_fields: set[str], field_name: str, question_text: str | None = None):
    if field_name in seen_fields:
        return

    if len(question_items) >= MAX_DESCRIPTION_QUESTIONS:
        return

    question_items.append(
        {
            "field": field_name,
            "question": question_text
            or FIELD_QUESTION_TEXT.get(field_name)
            or f"Please provide more detail for: {field_name}",
        }
    )
    seen_fields.add(field_name)


def _build_question_items(analysis: dict, customer_property_context: dict) -> list[dict]:
    """
    Builds the customer-facing question list.

    Policy:
    - Always ask truly missing blocking fields.
    - Also ask a few high-value confirmation questions.
    - Do not ask every optional add-on.
    - Cap at MAX_DESCRIPTION_QUESTIONS so the flow stays lightweight.
    """

    extracted = _clean_extracted_fields(analysis)
    final_preview = _apply_defaults_and_context(extracted, customer_property_context)

    model_missing_fields = analysis.get("missing_fields", []) or []

    map_context = customer_property_context.get("map_context", {}) or {}
    map_linear_feet = map_context.get("final_linear_feet")
    drawn_feet = map_context.get("drawn_feet")

    question_items = []
    seen_fields = set()

    # 1. Ask genuinely missing blocking fields first.
    for field_name in BLOCKING_FIELDS:
        if field_name in model_missing_fields or not _has_value(final_preview.get(field_name)):
            _add_question(
                question_items=question_items,
                seen_fields=seen_fields,
                field_name=field_name,
            )

    # 2. Ask the user to confirm map measurement when a map/fallback length is being used.
    # This prevents "silent" length assumptions.
    if map_linear_feet and "linear_feet" not in seen_fields:
        label = "map measurement" if drawn_feet else "entered fallback length"

        _add_question(
            question_items=question_items,
            seen_fields=seen_fields,
            field_name="linear_feet",
            question_text=(
                f"Should we use the {label} of {float(map_linear_feet):,.0f} ft for the estimate?"
            ),
        )

    # 3. Ask a small number of useful estimate-impact questions.
    # These are not hard blockers, but they make the estimate feel intentional.
    if not _has_value(extracted.get("material_grade")):
        _add_question(
            question_items=question_items,
            seen_fields=seen_fields,
            field_name="material_grade",
        )

    if not _has_value(extracted.get("access_level")):
        _add_question(
            question_items=question_items,
            seen_fields=seen_fields,
            field_name="access_level",
        )

    if not _has_value(extracted.get("brush_clearing")):
        _add_question(
            question_items=question_items,
            seen_fields=seen_fields,
            field_name="brush_clearing",
        )

    return question_items[:MAX_DESCRIPTION_QUESTIONS]


def _answer_payload(field: str, value, display_answer: str, answered: bool = True) -> dict:
    return {
        "field": field,
        "value": value,
        "display_answer": display_answer,
        "answered": answered,
    }


def render_question_input(question_item: dict, customer_property_context: dict) -> dict:
    field = question_item["field"]
    question = question_item["question"]

    map_context = customer_property_context.get("map_context", {}) or {}
    map_linear_feet = map_context.get("final_linear_feet")

    st.markdown(f"### {question}")

    key_base = f"description_question_{field}"

    if field == "linear_feet":
        if map_linear_feet:
            choice = st.radio(
                "Fence length source",
                [
                    f"Use map measurement: {float(map_linear_feet):,.0f} ft",
                    "Enter a different length",
                ],
                key=f"{key_base}_choice",
            )

            if choice.startswith("Use map measurement"):
                return _answer_payload(
                    field=field,
                    value=float(map_linear_feet),
                    display_answer=f"Use map measurement: {float(map_linear_feet):,.0f} ft",
                )

        entered_length = st.number_input(
            "Fence length in linear feet",
            min_value=1.0,
            value=float(map_linear_feet or 186.0),
            step=1.0,
            key=f"{key_base}_number",
        )

        return _answer_payload(
            field=field,
            value=float(entered_length),
            display_answer=f"{float(entered_length):,.0f} linear feet",
        )

    if field == "fence_type":
        value = st.selectbox(
            "Fence type",
            [
                "Select an option",
                "wood_privacy",
                "vinyl_privacy",
                "chain_link",
                "aluminum",
                "split_rail",
            ],
            format_func=lambda item: {
                "Select an option": "Select an option",
                "wood_privacy": "Wood privacy",
                "vinyl_privacy": "Vinyl privacy",
                "chain_link": "Chain link",
                "aluminum": "Aluminum",
                "split_rail": "Split rail",
            }[item],
            key=f"{key_base}_select",
        )

        if value == "Select an option":
            return _answer_payload(field, None, "", answered=False)

        return _answer_payload(field, value, value.replace("_", " ").title())

    if field == "height_ft":
        value = st.number_input(
            "Fence height",
            min_value=3,
            max_value=10,
            value=6,
            step=1,
            key=f"{key_base}_height",
        )

        return _answer_payload(field, int(value), f"{int(value)} ft")

    if field == "yard_location":
        value = st.selectbox(
            "Yard location",
            ["Select an option", "back", "side", "front"],
            format_func=lambda item: {
                "Select an option": "Select an option",
                "back": "Back yard",
                "side": "Side yard",
                "front": "Front yard",
            }[item],
            key=f"{key_base}_select",
        )

        if value == "Select an option":
            return _answer_payload(field, None, "", answered=False)

        return _answer_payload(field, value, value.replace("_", " ").title())

    if field == "gate_count":
        value = st.number_input(
            "Walk gates",
            min_value=0,
            value=1,
            step=1,
            key=f"{key_base}_number",
        )

        return _answer_payload(field, int(value), f"{int(value)} walk gate(s)")
    
    if field == "material_grade":
        value = st.selectbox(
            "Material grade",
            ["Select an option", "economy", "standard", "premium", "not_sure"],
            format_func=lambda item: {
                "Select an option": "Select an option",
                "economy": "Economy",
                "standard": "Standard",
                "premium": "Premium",
                "not_sure": "Not sure, use standard for now",
            }[item],
            key=f"{key_base}_select",
        )

        if value == "Select an option":
            return _answer_payload(field, None, "", answered=False)

        if value == "not_sure":
            return _answer_payload(field, "standard", "Not sure, use standard for now")

        return _answer_payload(field, value, value.title())

    if field == "access_level":
        value = st.selectbox(
            "Access to fence area",
            ["Select an option", "easy", "limited", "difficult", "not_sure"],
            format_func=lambda item: {
                "Select an option": "Select an option",
                "easy": "Easy access",
                "limited": "Limited access",
                "difficult": "Difficult access",
                "not_sure": "Not sure, assume easy for now",
            }[item],
            key=f"{key_base}_select",
        )

        if value == "Select an option":
            return _answer_payload(field, None, "", answered=False)

        if value == "not_sure":
            return _answer_payload(field, "easy", "Not sure, assume easy for now")

        return _answer_payload(field, value, value.replace("_", " ").title())

    if field == "brush_clearing":
        value = st.selectbox(
            "Brush or obstruction clearing",
            ["Select an option", "none", "light", "moderate", "heavy", "not_sure"],
            format_func=lambda item: {
                "Select an option": "Select an option",
                "none": "None",
                "light": "Light",
                "moderate": "Moderate",
                "heavy": "Heavy",
                "not_sure": "Not sure, assume none for now",
            }[item],
            key=f"{key_base}_select",
        )

        if value == "Select an option":
            return _answer_payload(field, None, "", answered=False)

        if value == "not_sure":
            return _answer_payload(field, "none", "Not sure, assume none for now")

        return _answer_payload(field, value, value.title())

    answer = st.text_input(
        "Answer",
        key=f"{key_base}_text",
    )

    if not answer.strip():
        return _answer_payload(field, None, "", answered=False)

    return _answer_payload(field, answer.strip(), answer.strip())


def build_final_fields_from_description(customer_property_context: dict) -> dict:
    analysis = st.session_state.get("intake_analysis") or {}
    answers = st.session_state.get("description_missing_answers") or {}

    extracted = _clean_extracted_fields(analysis)
    final_fields = _apply_defaults_and_context(extracted, customer_property_context)

    for field, answer_payload in answers.items():
        if not answer_payload:
            continue

        value = answer_payload.get("value")

        if value is None:
            continue

        final_fields[field] = value

    final_fields = _apply_defaults_and_context(final_fields, customer_property_context)

    notes_parts = []

    raw_description = st.session_state.get("raw_project_description", "")
    if raw_description.strip():
        notes_parts.append(f"Customer description:\n{raw_description.strip()}")

    summary = analysis.get("summary")
    if summary:
        notes_parts.append(f"AI intake summary:\n{summary}")

    answer_lines = []

    for answer_payload in answers.values():
        display_answer = answer_payload.get("display_answer")
        field = answer_payload.get("field")

        if display_answer:
            answer_lines.append(f"- {field}: {display_answer}")

    if answer_lines:
        notes_parts.append("Description follow-up answers:\n" + "\n".join(answer_lines))

    existing_notes = final_fields.get("customer_notes")
    if existing_notes:
        notes_parts.append(str(existing_notes))

    if notes_parts:
        final_fields["customer_notes"] = "\n\n".join(notes_parts)

    return final_fields


def missing_required_for_description_payload(final_fields: dict) -> list[str]:
    missing = []

    for field_name in BLOCKING_FIELDS:
        if not _has_value(final_fields.get(field_name)):
            missing.append(field_name)

    return missing

def build_flat_missing_answers() -> dict[str, str]:
    """
    Converts the description-question answer payloads into the shape expected
    by backend.models.EstimateRequest.

    Backend expects:
        dict[str, str]

    Not:
        dict[str, dict]
    """

    answers = st.session_state.get("description_missing_answers") or {}

    flat_answers = {}

    for field, answer_payload in answers.items():
        if not answer_payload:
            continue

        display_answer = answer_payload.get("display_answer")

        if display_answer:
            flat_answers[field] = str(display_answer)

    return flat_answers

def build_description_estimate_payload(
    customer_property_context: dict,
    final_fields: dict,
) -> dict:
    linear_feet = _safe_float(final_fields.get("linear_feet"), 0.0)
    height_ft = _safe_int(final_fields.get("height_ft"), 6)
    yard_location = final_fields.get("yard_location") or "back"

    yard_sections = [
        {
            "location": yard_location,
            "included": True,
            "height_ft": height_ft,
            "linear_feet": linear_feet,
        }
    ]

    access_level = final_fields.get("access_level") or "easy"
    slope_severity = final_fields.get("slope_severity") or "none"

    difficult_access = access_level in ["limited", "difficult"] or _safe_bool(
        final_fields.get("difficult_access"),
        False,
    )

    slope_present = slope_severity != "none" or _safe_bool(
        final_fields.get("slope_present"),
        False,
    )

    return {
        "customer_name": customer_property_context.get("customer_name"),
        "customer_email": customer_property_context.get("customer_email"),
        "customer_phone": customer_property_context.get("customer_phone"),
        "address": customer_property_context.get("selected_address"),
        "property_lat": customer_property_context.get("property_lat"),
        "property_lng": customer_property_context.get("property_lng"),
        "fence_type": final_fields.get("fence_type"),
        "height_ft": height_ft,
        "linear_feet": linear_feet,
        "yard_location": yard_location,
        "yard_sections": yard_sections,
        "gate_count": _safe_int(final_fields.get("gate_count"), 0),
        "double_gate_count": _safe_int(final_fields.get("double_gate_count"), 0),
        "old_fence_removal": _safe_bool(final_fields.get("old_fence_removal"), False),
        "difficult_access": difficult_access,
        "slope_present": slope_present,
        "material_grade": final_fields.get("material_grade") or "standard",
        "gate_hardware": final_fields.get("gate_hardware") or "standard",
        "removal_length_feet": linear_feet
        if _safe_bool(final_fields.get("old_fence_removal"), False)
        else 0.0,
        "slope_severity": slope_severity,
        "access_level": access_level,
        "brush_clearing": final_fields.get("brush_clearing") or "none",
        "stain_seal": _safe_bool(final_fields.get("stain_seal"), False),
        "permit_admin": _safe_bool(final_fields.get("permit_admin"), False),
        "customer_notes": final_fields.get("customer_notes") or "",
        "missing_answers": build_flat_missing_answers(),
    }


def finalize_description_question_flow(customer_property_context: dict):
    final_fields = build_final_fields_from_description(customer_property_context)

    st.session_state.prefilled_fields = final_fields
    st.session_state.description_stage = "review_details"
    st.session_state.guided_form_prefill_applied = False

    reset_guided_review_state()


def run_description_intake_analysis(
    customer_property_context: dict,
    raw_description: str,
):
    payload = build_intake_request_payload(
        customer_property_context=customer_property_context,
        raw_description=raw_description,
    )

    with st.status("Analyzing your project description...", expanded=True) as status:
        try:
            st.write("Analyzing the description...")
            st.write("Extracting fence project details...")

            analysis = analyze_text_intake_request(payload)

            st.write("Generating missing questions...")

            question_items = _build_question_items(
                analysis=analysis,
                customer_property_context=customer_property_context,
            )

            st.session_state.intake_analysis = analysis
            st.session_state.description_missing_questions = question_items
            st.session_state.description_missing_answers = {}
            st.session_state.description_current_question_index = 0
            st.session_state.description_analysis_error = None

            reset_guided_review_state()

            if not analysis.get("is_relevant"):
                st.session_state.description_stage = "analyzed"
            elif question_items:
                st.session_state.description_stage = "asking_questions"
            else:
                finalize_description_question_flow(customer_property_context)

            status.update(
                label="Description analysis complete.",
                state="complete",
            )

        except requests.exceptions.RequestException as error:
            st.session_state.description_analysis_error = str(error)
            st.session_state.description_stage = "idle"

            st.error(f"Could not analyze project description: {error}")

            response = getattr(error, "response", None)
            if response is not None:
                try:
                    st.code(response.text)
                except Exception:
                    pass

            status.update(
                label="Description analysis failed.",
                state="error",
            )


def render_description_question_flow(customer_property_context: dict):
    analysis = st.session_state.get("intake_analysis") or {}
    question_items = st.session_state.get("description_missing_questions") or []

    if not question_items:
        finalize_description_question_flow(customer_property_context)
        st.rerun()

    idx = st.session_state.description_current_question_index
    total = len(question_items)

    idx = max(0, min(idx, total - 1))
    question_item = question_items[idx]

    st.success("We understood the main project details. We just need a few more answers.")

    if analysis.get("summary"):
        st.write(f"**Project summary:** {analysis.get('summary')}")

    st.markdown(f"### Question {idx + 1} of {total}")
    st.progress((idx + 1) / total)

    with st.container(border=True):
        answer_payload = render_question_input(question_item, customer_property_context)

    st.session_state.description_missing_answers[question_item["field"]] = answer_payload

    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 2])

    with nav_col1:
        if st.button("Back", disabled=idx == 0, key="description_question_back"):
            st.session_state.description_current_question_index = max(0, idx - 1)
            st.rerun()

    with nav_col2:
        is_answered = bool(answer_payload.get("answered"))

        if idx < total - 1:
            if st.button("Next", type="primary", key="description_question_next"):
                if not is_answered:
                    st.warning("Please answer this question before continuing.")
                else:
                    st.session_state.description_current_question_index = idx + 1
                    st.rerun()
        else:
            if st.button("Done", type="primary", key="description_question_done"):
                if not is_answered:
                    st.warning("Please answer this question before continuing.")
                else:
                    finalize_description_question_flow(customer_property_context)
                    st.rerun()

    with nav_col3:
        answered_count = sum(
            1
            for answer in st.session_state.description_missing_answers.values()
            if answer and answer.get("answered")
        )
        st.caption(f"Answered {answered_count} of {total} follow-up questions.")


def render_not_relevant_result():
    analysis = st.session_state.get("intake_analysis") or {}

    st.error(
        analysis.get(
            "user_message",
            "This does not look like a fence estimate request.",
        )
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("Try another description", key="try_another_description"):
            reset_description_intake_state()
            reset_guided_review_state()
            st.rerun()

    with col2:
        if st.button("Use guided form instead", key="not_relevant_guided_form"):
            st.session_state.intake_mode = GUIDED_FORM_MODE
            reset_guided_review_state()
            st.rerun()


def render_idle_description_entry(customer_property_context: dict):
    render_description_guidance()

    raw_description = render_description_text_area()
    description_ready = bool(raw_description and raw_description.strip())

    st.divider()

    action_col1, action_col2 = st.columns([1, 1])

    with action_col1:
        if st.button(
            "Analyze Description",
            type="primary",
            disabled=not description_ready,
            key="analyze_description_button",
        ):
            run_description_intake_analysis(
                customer_property_context=customer_property_context,
                raw_description=raw_description,
            )
            st.rerun()

    with action_col2:
        if st.button(
            "Continue with guided form instead",
            key="description_to_guided_form",
        ):
            st.session_state.intake_mode = GUIDED_FORM_MODE
            reset_guided_review_state()
            st.rerun()

    if not description_ready:
        st.info("Write a project description to continue.")


def render_review_details(customer_property_context: dict):
    final_fields = build_final_fields_from_description(customer_property_context)
    missing_required = missing_required_for_description_payload(final_fields)

    st.success("Thanks. We have enough information to review the estimate details.")

    with st.container(border=True):
        st.markdown("### Review Estimate Details")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.write(f"**Fence type:** {fence_type_label(final_fields.get('fence_type'))}")
            st.write(f"**Height:** {_safe_int(final_fields.get('height_ft'), 0)} ft")
            st.write(f"**Length:** {_safe_float(final_fields.get('linear_feet'), 0):,.1f} ft")

        with col2:
            st.write(f"**Yard:** {yard_location_label(final_fields.get('yard_location'))}")
            st.write(f"**Walk gates:** {_safe_int(final_fields.get('gate_count'), 0)}")
            st.write(f"**Double gates:** {_safe_int(final_fields.get('double_gate_count'), 0)}")

        with col3:
            st.write(
                f"**Old fence removal:** {'Yes' if _safe_bool(final_fields.get('old_fence_removal'), False) else 'No'}"
            )
            st.write(f"**Slope:** {status_label(final_fields.get('slope_severity'))}")
            st.write(f"**Access:** {status_label(final_fields.get('access_level'))}")

    with st.expander("Assumptions used for preliminary estimate", expanded=False):
        st.write(f"**Material grade:** {status_label(final_fields.get('material_grade'))}")
        st.write(f"**Gate hardware:** {status_label(final_fields.get('gate_hardware'))}")
        st.write(f"**Brush clearing:** {status_label(final_fields.get('brush_clearing'))}")
        st.write(
            f"**Stain/seal:** {'Yes' if _safe_bool(final_fields.get('stain_seal'), False) else 'No'}"
        )
        st.write(
            f"**Permit/HOA support:** {'Yes' if _safe_bool(final_fields.get('permit_admin'), False) else 'No'}"
        )

    if missing_required:
        st.error(
            "Some required details are still missing: "
            + ", ".join(missing_required)
            + ". Please use the full guided form to complete them."
        )

    action_col1, action_col2 = st.columns([1, 1])

    with action_col1:
        if st.button("Edit full form", key="description_edit_full_form"):
            st.session_state.prefilled_fields = final_fields
            st.session_state.guided_form_prefill_applied = False
            st.session_state.intake_mode = GUIDED_FORM_MODE
            reset_guided_review_state()
            st.rerun()

    with action_col2:
        if st.button("Start over", key="description_review_start_over"):
            reset_description_intake_state()
            reset_guided_review_state()
            st.rerun()

    if missing_required:
        return

    payload = build_description_estimate_payload(
        customer_property_context=customer_property_context,
        final_fields=final_fields,
    )

    st.divider()

    render_guided_estimate_workflow(
        payload=payload,
        customer_notes=payload.get("customer_notes", ""),
        skip_missing_questions=True,
        section_title="Generate Estimate",
        intro_copy=(
            "FenceScope will run the compliance pre-check, generate the preliminary estimate, "
            "and save the result for admin review. Since you already answered the description follow-up questions, "
            "we will not ask another customer questionnaire here."
        ),
        start_button_label="Generate Estimate",
    )


def render_description_intake(customer_property_context: dict):
    st.subheader("Project Description Intake")

    st.caption(
        "Describe the fence project naturally. FenceScope will analyze the description, "
        "ask only the important missing questions, and then generate a preliminary estimate."
    )

    stage = st.session_state.get("description_stage", "idle")

    if stage == "idle":
        render_idle_description_entry(customer_property_context)
        return

    if stage == "analyzed":
        render_not_relevant_result()
        return

    if stage == "asking_questions":
        render_description_question_flow(customer_property_context)
        return

    if stage == "review_details":
        render_review_details(customer_property_context)
        return

    st.warning("Unknown description intake stage. Restarting description intake.")
    reset_description_intake_state()
    reset_guided_review_state()