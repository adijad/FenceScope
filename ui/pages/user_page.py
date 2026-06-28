# ui/pages/user_page.py

import streamlit as st

from ui.components.guided_form import render_guided_form_payload
from ui.workflows.guided_review import render_guided_estimate_workflow


def render_user_view():
    st.title("FenceScope AI")
    st.caption(
        "AI-assisted estimate triage and proposal workflow for residential fencing companies."
    )

    form_result = render_guided_form_payload()

    payload = form_result["payload"]
    customer_notes = form_result["customer_notes"]

    render_guided_estimate_workflow(payload, customer_notes)