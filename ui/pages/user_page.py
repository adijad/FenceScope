# ui/pages/user_page.py

import streamlit as st

from ui.components.description_intake import render_description_intake
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

def render_user_view():
    if not st.session_state.get("user_started"):
        render_welcome_step()
        return

    st.title("FenceScope AI")

    st.caption(
        "Your AI-assisted fence estimator."
    )

    customer_property_context = render_customer_property_setup(
        compact_when_ready=bool(st.session_state.get("intake_mode"))
    )

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
        render_description_intake(customer_property_context)
        return

    st.warning("Unknown intake mode selected. Please choose an estimate path again.")
    st.session_state.intake_mode = None