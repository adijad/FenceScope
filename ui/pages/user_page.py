# ui/pages/user_page.py

import streamlit as st

from ui.components.guided_form import render_guided_form_payload
from ui.components.intake_choice import (
    DESCRIPTION_MODE,
    GUIDED_FORM_MODE,
    render_intake_choice,
)
from ui.components.property_setup import render_customer_property_setup
from ui.workflows.guided_review import render_guided_estimate_workflow


def render_welcome_step():
    st.title("Welcome to FenceScope AI")

    st.caption("Your AI-assisted fence estimator.")

    st.markdown(
        """
        Start by entering your customer and property details. After the address is selected, 
        you will be able to confirm the property on a map, optionally draw the fence layout, 
        and then choose how you want to continue.
        """
    )

    if st.button("Let's get started", type="primary", key="start_user_flow"):
        st.session_state.user_started = True
        st.session_state.intake_mode = None
        st.rerun()


def render_description_placeholder(customer_property_context: dict):
    st.subheader("Project Description Intake")

    st.info(
        "This path is ready structurally. Next, we will connect it to a guardrailed LLM intake agent."
    )

    st.write("The description agent will receive this shared context:")

    context_preview = {
        "customer_name": customer_property_context.get("customer_name"),
        "customer_email": customer_property_context.get("customer_email"),
        "customer_phone": customer_property_context.get("customer_phone"),
        "address": customer_property_context.get("selected_address"),
        "property_lat": customer_property_context.get("property_lat"),
        "property_lng": customer_property_context.get("property_lng"),
        "map_linear_feet": (
            customer_property_context.get("map_context", {}).get("final_linear_feet")
        ),
        "gate_markers": (
            len(customer_property_context.get("map_context", {}).get("gate_points", []))
        ),
    }

    st.json(context_preview)

    raw_description = st.text_area(
        "Describe your fence project",
        value=st.session_state.get("raw_project_description", ""),
        height=180,
        placeholder=(
            "Example: I want a 6 ft wood privacy fence around my backyard. "
            "We have two dogs, need one walk gate, and there is an old chain link fence "
            "that may need to be removed."
        ),
        key="description_intake_text_area",
    )

    st.session_state.raw_project_description = raw_description

    st.caption(
        "For now, this only captures the description. The next step will send it to the backend LLM intake endpoint."
    )

    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("Continue with guided form instead", key="description_to_guided_form"):
            st.session_state.intake_mode = GUIDED_FORM_MODE
            st.rerun()

    with col2:
        st.caption(
            "The LLM will not create an estimate directly. It will extract a draft, show missing details, and then route back into the guided estimate review."
        )


def render_user_view():
    if not st.session_state.get("user_started"):
        render_welcome_step()
        return

    st.title("FenceScope AI")

    st.caption(
        "AI-assisted estimate triage and proposal workflow for residential fencing companies."
    )

    customer_property_context = render_customer_property_setup()

    if not customer_property_context.get("address_selected"):
        return

    st.divider()

    intake_mode = render_intake_choice()

    if intake_mode is None:
        st.info("Choose one of the estimate paths above to continue.")
        return

    st.divider()

    if intake_mode == GUIDED_FORM_MODE:
        form_result = render_guided_form_payload(customer_property_context)

        payload = form_result["payload"]
        customer_notes = form_result["customer_notes"]

        render_guided_estimate_workflow(payload, customer_notes)
        return

    if intake_mode == DESCRIPTION_MODE:
        render_description_placeholder(customer_property_context)
        return

    st.warning("Unknown intake mode selected. Please choose an estimate path again.")
    st.session_state.intake_mode = None