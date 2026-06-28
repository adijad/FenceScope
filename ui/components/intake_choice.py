# ui/components/intake_choice.py

import streamlit as st


GUIDED_FORM_MODE = "guided_form"
DESCRIPTION_MODE = "description"


def reset_intake_choice():
    st.session_state.intake_mode = None


def render_intake_choice():
    """
    Renders the branch point after customer/property/map setup.

    Returns:
        "guided_form"
        "description"
        None
    """

    st.subheader("How would you like to start your fence estimate?")

    st.caption(
        "You can either fill out a guided form or describe the project in your own words. "
        "Both paths will still use the property address and map context above."
    )

    selected_mode = st.session_state.get("intake_mode")

    if selected_mode:
        selected_label = {
            GUIDED_FORM_MODE: "Guided form",
            DESCRIPTION_MODE: "Project description",
        }.get(selected_mode, selected_mode)

        st.success(f"Selected path: {selected_label}")

        if st.button("Change estimate path", key="change_intake_mode"):
            reset_intake_choice()
            st.rerun()

        return selected_mode

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("### Fill a guided form")
            st.write(
                "Best when you already know the fence type, height, length, gates, "
                "removal needs, slope, and access details."
            )

            if st.button(
                "Use Guided Form",
                type="primary",
                key="select_guided_form_mode",
            ):
                st.session_state.intake_mode = GUIDED_FORM_MODE
                st.rerun()

    with col2:
        with st.container(border=True):
            st.markdown("### Write your project description")
            st.write(
                "Best when you want to explain the project naturally and let the AI "
                "identify useful estimate details."
            )

            if st.button(
                "Write Description",
                type="primary",
                key="select_description_mode",
            ):
                st.session_state.intake_mode = DESCRIPTION_MODE
                st.rerun()

    return None