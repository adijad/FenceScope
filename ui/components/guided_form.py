# ui/components/guided_form.py

import json

import streamlit as st

from ui.components.gate_plan import render_map_gate_plan
from ui.components.property_setup import render_customer_property_setup
from ui.components.yard_sections import (
    derive_primary_yard_location,
    render_yard_sections,
)
from ui.state import reset_workflow_state


FENCE_TYPE_OPTIONS = [
    "wood_privacy",
    "vinyl_privacy",
    "chain_link",
    "aluminum",
    "split_rail",
]

MATERIAL_GRADE_OPTIONS = [
    "economy",
    "standard",
    "premium",
]

GATE_HARDWARE_OPTIONS = [
    "standard",
    "self_closing",
    "lockable",
]

ACCESS_LEVEL_OPTIONS = [
    "easy",
    "limited",
    "difficult",
]

SLOPE_SEVERITY_OPTIONS = [
    "none",
    "slight",
    "moderate",
    "steep",
]

BRUSH_CLEARING_OPTIONS = [
    "none",
    "light",
    "moderate",
    "heavy",
]


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


def _valid_option(value, options):
    if value in options:
        return value

    return None


def _get_map_context(customer_property_context: dict) -> dict:
    return customer_property_context.get("map_context") or {}


def _get_prefilled_fields() -> dict:
    return st.session_state.get("prefilled_fields") or {}


def _get_shared_linear_feet(customer_property_context: dict) -> float:
    prefilled = _get_prefilled_fields()
    map_context = _get_map_context(customer_property_context)

    return _safe_float(
        prefilled.get("linear_feet")
        or map_context.get("final_linear_feet")
        or map_context.get("fallback_linear_feet")
        or 186.0,
        default=186.0,
    )


def _index_for_option(options: list[str], value, default_index: int = 0) -> int:
    if value in options:
        return options.index(value)

    return default_index


def _apply_guided_form_prefill_defaults():
    """
    Applies description-intake extracted fields to Streamlit widget state.

    This runs before widgets are rendered. The user can still edit every field.
    """
    prefilled = _get_prefilled_fields()

    if not prefilled:
        return

    if st.session_state.get("guided_form_prefill_applied"):
        return

    fence_type = _valid_option(prefilled.get("fence_type"), FENCE_TYPE_OPTIONS)
    if fence_type:
        st.session_state["fence_type"] = fence_type

    material_grade = _valid_option(prefilled.get("material_grade"), MATERIAL_GRADE_OPTIONS)
    if material_grade:
        st.session_state["material_grade"] = material_grade

    gate_hardware = _valid_option(prefilled.get("gate_hardware"), GATE_HARDWARE_OPTIONS)
    if gate_hardware:
        st.session_state["gate_hardware"] = gate_hardware

    access_level = _valid_option(prefilled.get("access_level"), ACCESS_LEVEL_OPTIONS)
    if access_level:
        st.session_state["access_level"] = access_level

    slope_severity = _valid_option(prefilled.get("slope_severity"), SLOPE_SEVERITY_OPTIONS)
    if slope_severity:
        st.session_state["slope_severity"] = slope_severity
    elif prefilled.get("slope_present") is True:
        st.session_state["slope_severity"] = "slight"

    brush_clearing = _valid_option(prefilled.get("brush_clearing"), BRUSH_CLEARING_OPTIONS)
    if brush_clearing:
        st.session_state["brush_clearing"] = brush_clearing

    if prefilled.get("height_ft") is not None:
        st.session_state["height_ft"] = _safe_int(prefilled.get("height_ft"), 6)

    if prefilled.get("linear_feet") is not None:
        st.session_state["linear_feet_for_estimate"] = _safe_float(
            prefilled.get("linear_feet"),
            186.0,
        )

    if prefilled.get("gate_count") is not None:
        st.session_state["gate_count"] = _safe_int(prefilled.get("gate_count"), 0)

    if prefilled.get("double_gate_count") is not None:
        st.session_state["double_gate_count"] = _safe_int(
            prefilled.get("double_gate_count"),
            0,
        )

    if prefilled.get("old_fence_removal") is not None:
        st.session_state["old_fence_removal"] = _safe_bool(
            prefilled.get("old_fence_removal"),
            False,
        )

    if prefilled.get("stain_seal") is not None:
        st.session_state["stain_seal"] = _safe_bool(
            prefilled.get("stain_seal"),
            False,
        )

    if prefilled.get("permit_admin") is not None:
        st.session_state["permit_admin"] = _safe_bool(
            prefilled.get("permit_admin"),
            False,
        )

    if prefilled.get("customer_notes"):
        st.session_state["customer_notes"] = prefilled.get("customer_notes")

    st.session_state.guided_form_prefill_applied = True


def _set_payload_fingerprint(payload: dict):
    """
    Tracks whether project details changed after a review was started.

    If the user changes project details, the review workflow must restart.
    """
    payload_fingerprint = json.dumps(payload, sort_keys=True)

    if (
        st.session_state.last_payload_fingerprint is not None
        and st.session_state.last_payload_fingerprint != payload_fingerprint
    ):
        reset_workflow_state()
        st.session_state.last_payload_fingerprint = payload_fingerprint
        st.info("Project details changed. Start the estimate review again.")
        return

    if st.session_state.last_payload_fingerprint is None:
        st.session_state.last_payload_fingerprint = payload_fingerprint


def render_prefill_notice():
    prefilled = _get_prefilled_fields()

    if not prefilled:
        return

    with st.container(border=True):
        st.success("Guided form prefilled from your project description.")
        st.caption(
            "Review these details before starting the estimate review. You can edit anything below."
        )


def render_map_measurement_summary(customer_property_context: dict):
    map_context = _get_map_context(customer_property_context)

    drawn_feet = map_context.get("drawn_feet")
    use_map_measurement = map_context.get("use_map_measurement")
    final_linear_feet = _safe_float(map_context.get("final_linear_feet"), default=0.0)
    gate_points = map_context.get("gate_points", [])

    st.subheader("4. Fence Project Details")

    with st.container(border=True):
        st.markdown("**Shared property/map context**")

        if drawn_feet:
            st.success(f"Map measurement detected: {float(drawn_feet):,.2f} linear feet")
        else:
            st.info("No map fence line detected. The estimate will use the length entered below.")

        if use_map_measurement and final_linear_feet > 0:
            st.write(f"**Current length from shared setup:** {final_linear_feet:,.2f} ft")
        elif final_linear_feet > 0:
            st.write(f"**Current fallback length from shared setup:** {final_linear_feet:,.2f} ft")

        if gate_points:
            st.write(f"**Gate markers detected:** {len(gate_points)}")
        else:
            st.write("**Gate markers detected:** 0")


def render_job_details(customer_property_context: dict):
    """
    Renders only the structured fence/job details.

    Customer details, address selection, and map drawing are handled by property_setup.py.
    """

    _apply_guided_form_prefill_defaults()

    prefilled = _get_prefilled_fields()
    shared_linear_feet = _get_shared_linear_feet(customer_property_context)

    render_prefill_notice()
    render_map_measurement_summary(customer_property_context)

    job_col1, job_col2 = st.columns(2)

    with job_col1:
        fence_type_default = st.session_state.get(
            "fence_type",
            prefilled.get("fence_type") or "wood_privacy",
        )

        fence_type = st.selectbox(
            "Fence type",
            FENCE_TYPE_OPTIONS,
            index=_index_for_option(FENCE_TYPE_OPTIONS, fence_type_default, 0),
            key="fence_type",
        )

        material_grade_default = st.session_state.get(
            "material_grade",
            prefilled.get("material_grade") or "standard",
        )

        material_grade = st.selectbox(
            "Material grade",
            MATERIAL_GRADE_OPTIONS,
            index=_index_for_option(MATERIAL_GRADE_OPTIONS, material_grade_default, 1),
            help="Adjusts the per-foot material/install rate.",
            key="material_grade",
        )

        height_ft = st.number_input(
            "Default fence height",
            min_value=3,
            max_value=10,
            value=_safe_int(st.session_state.get("height_ft", prefilled.get("height_ft") or 6), 6),
            step=1,
            help="Used as the default height for yard sections below.",
            key="height_ft",
        )

        linear_feet_for_estimate = st.number_input(
            "Fence length for estimate",
            min_value=1.0,
            value=_safe_float(
                st.session_state.get("linear_feet_for_estimate", shared_linear_feet),
                shared_linear_feet,
            ),
            step=1.0,
            key="linear_feet_for_estimate",
            help=(
                "This defaults to the map measurement or the value extracted from the project description. "
                "You can adjust it before generating the estimate."
            ),
        )

        stain_seal = st.checkbox(
            "Add stain/seal option",
            value=_safe_bool(st.session_state.get("stain_seal", prefilled.get("stain_seal")), False),
            help="Adds a per-foot stain or seal add-on.",
            key="stain_seal",
        )

        access_level_default = st.session_state.get(
            "access_level",
            prefilled.get("access_level") or "easy",
        )

        access_level = st.selectbox(
            "Access level",
            ACCESS_LEVEL_OPTIONS,
            index=_index_for_option(ACCESS_LEVEL_OPTIONS, access_level_default, 0),
            help="Adds a complexity adjustment for limited crew/material access.",
            key="access_level",
        )

    with job_col2:
        gate_count = st.number_input(
            "Walk gates",
            min_value=0,
            value=_safe_int(st.session_state.get("gate_count", prefilled.get("gate_count") or 2), 2),
            step=1,
            key="gate_count",
        )

        double_gate_count = st.number_input(
            "Double gates",
            min_value=0,
            value=_safe_int(
                st.session_state.get("double_gate_count", prefilled.get("double_gate_count") or 0),
                0,
            ),
            step=1,
            key="double_gate_count",
        )

        gate_hardware_default = st.session_state.get(
            "gate_hardware",
            prefilled.get("gate_hardware") or "standard",
        )

        gate_hardware = st.selectbox(
            "Gate hardware",
            GATE_HARDWARE_OPTIONS,
            index=_index_for_option(GATE_HARDWARE_OPTIONS, gate_hardware_default, 0),
            help="Adds hardware upgrade cost per gate.",
            key="gate_hardware",
        )

        old_fence_removal = st.checkbox(
            "Old fence removal required",
            value=_safe_bool(
                st.session_state.get(
                    "old_fence_removal",
                    prefilled.get("old_fence_removal"),
                ),
                True,
            ),
            key="old_fence_removal",
        )

        removal_length_feet = 0.0

        if old_fence_removal:
            removal_length_feet = st.number_input(
                "Approx. old fence removal length",
                min_value=0.0,
                value=_safe_float(
                    st.session_state.get("removal_length_feet", linear_feet_for_estimate),
                    linear_feet_for_estimate,
                ),
                step=1.0,
                help=(
                    "Use 0 if unknown. The pricing engine will fall back to total fence length."
                ),
                key="removal_length_feet",
            )

        slope_severity_default = st.session_state.get(
            "slope_severity",
            prefilled.get("slope_severity") or "moderate",
        )

        slope_severity = st.selectbox(
            "Slope severity",
            SLOPE_SEVERITY_OPTIONS,
            index=_index_for_option(SLOPE_SEVERITY_OPTIONS, slope_severity_default, 2),
            help="Adds a complexity adjustment based on slope.",
            key="slope_severity",
        )

        brush_clearing_default = st.session_state.get(
            "brush_clearing",
            prefilled.get("brush_clearing") or "none",
        )

        brush_clearing = st.selectbox(
            "Brush / obstruction clearing",
            BRUSH_CLEARING_OPTIONS,
            index=_index_for_option(BRUSH_CLEARING_OPTIONS, brush_clearing_default, 0),
            key="brush_clearing",
        )

        permit_admin = st.checkbox(
            "Permit / HOA admin support",
            value=_safe_bool(st.session_state.get("permit_admin", prefilled.get("permit_admin")), False),
            help="Adds a fixed admin support line item.",
            key="permit_admin",
        )

    difficult_access = access_level in ["limited", "difficult"]
    slope_present = slope_severity != "none"

    default_notes = (
        "Backyard slopes slightly. HOA neighborhood. We have two dogs and an old "
        "chain link fence that needs to be removed. Wants quote quickly."
    )

    customer_notes = st.text_area(
        "Customer / property notes",
        value=st.session_state.get(
            "customer_notes",
            prefilled.get("customer_notes") or default_notes,
        ),
        height=140,
        key="customer_notes",
    )

    return {
        "fence_type": fence_type,
        "material_grade": material_grade,
        "height_ft": height_ft,
        "linear_feet_for_estimate": linear_feet_for_estimate,
        "stain_seal": stain_seal,
        "access_level": access_level,
        "gate_count": gate_count,
        "double_gate_count": double_gate_count,
        "gate_hardware": gate_hardware,
        "old_fence_removal": old_fence_removal,
        "removal_length_feet": removal_length_feet,
        "slope_severity": slope_severity,
        "brush_clearing": brush_clearing,
        "permit_admin": permit_admin,
        "difficult_access": difficult_access,
        "slope_present": slope_present,
        "customer_notes": customer_notes,
    }


def build_estimate_payload(
    customer_property_context: dict,
    job_details: dict,
    final_linear_feet: float,
    final_gate_count: int,
    final_double_gate_count: int,
    yard_sections: list[dict],
    yard_location: str,
    gate_plan_notes: str,
):
    customer_notes = job_details["customer_notes"]

    return {
        "customer_name": customer_property_context["customer_name"],
        "customer_email": customer_property_context["customer_email"],
        "customer_phone": customer_property_context["customer_phone"],
        "address": customer_property_context["selected_address"],
        "property_lat": customer_property_context["property_lat"],
        "property_lng": customer_property_context["property_lng"],
        "fence_type": job_details["fence_type"],
        "height_ft": job_details["height_ft"],
        "linear_feet": final_linear_feet,
        "yard_location": yard_location,
        "yard_sections": yard_sections,
        "gate_count": final_gate_count,
        "double_gate_count": final_double_gate_count,
        "old_fence_removal": job_details["old_fence_removal"],
        "difficult_access": job_details["difficult_access"],
        "slope_present": job_details["slope_present"],
        "material_grade": job_details["material_grade"],
        "gate_hardware": job_details["gate_hardware"],
        "removal_length_feet": (
            job_details["removal_length_feet"]
            if job_details["old_fence_removal"]
            else 0.0
        ),
        "slope_severity": job_details["slope_severity"],
        "access_level": job_details["access_level"],
        "brush_clearing": job_details["brush_clearing"],
        "stain_seal": job_details["stain_seal"],
        "permit_admin": job_details["permit_admin"],
        "customer_notes": customer_notes + gate_plan_notes,
    }


def render_guided_form_payload(customer_property_context: dict | None = None):
    """
    Renders the guided form details and returns:

    {
        "payload": EstimateRequest-compatible dict,
        "customer_notes": raw customer notes before gate-plan notes,
        "drawn_feet": map measurement if available
    }
    """

    if customer_property_context is None:
        customer_property_context = render_customer_property_setup()
        st.divider()

    job_details = render_job_details(customer_property_context)

    map_context = _get_map_context(customer_property_context)
    gate_points = map_context.get("gate_points", [])

    final_linear_feet = float(job_details["linear_feet_for_estimate"])

    st.divider()

    gate_plan_result = render_map_gate_plan(
        gate_points=gate_points,
        manual_walk_gates=job_details["gate_count"],
        manual_double_gates=job_details["double_gate_count"],
    )

    final_gate_count = gate_plan_result["final_gate_count"]
    final_double_gate_count = gate_plan_result["final_double_gate_count"]
    gate_plan_notes = gate_plan_result["gate_plan_notes"]

    st.divider()

    yard_sections = render_yard_sections(
        default_height_ft=job_details["height_ft"],
        total_linear_feet=final_linear_feet,
    )

    yard_location = derive_primary_yard_location(yard_sections)

    st.divider()

    payload = build_estimate_payload(
        customer_property_context=customer_property_context,
        job_details=job_details,
        final_linear_feet=final_linear_feet,
        final_gate_count=final_gate_count,
        final_double_gate_count=final_double_gate_count,
        yard_sections=yard_sections,
        yard_location=yard_location,
        gate_plan_notes=gate_plan_notes,
    )

    _set_payload_fingerprint(payload)

    return {
        "payload": payload,
        "customer_notes": job_details["customer_notes"],
        "drawn_feet": map_context.get("drawn_feet"),
    }