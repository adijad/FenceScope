# ui/components/intake_choice.py

import streamlit as st


GUIDED_FORM_MODE = "guided_form"
DESCRIPTION_MODE = "description"
VOICE_MODE = "voice"


def reset_intake_choice():
    st.session_state.intake_mode = None


def render_intake_choice():
    """
    Renders the branch point after customer/property/map setup.

    Returns:
        "guided_form"
        "description"
        "voice"
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
            VOICE_MODE: "Talk about your project",
        }.get(selected_mode, selected_mode)

        st.success(f"Selected path: {selected_label}")

        if st.button("Change estimate path", key="change_intake_mode"):
            reset_intake_choice()
            st.rerun()

        return selected_mode

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="fs-card">
                <div class="fs-card-icon">📋</div>
                <div class="fs-card-title">Fill a guided form</div>
                <div class="fs-card-copy">
                    Best when you already know the fence type, height, length, gates,
                    removal needs, slope, and access details.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Use Guided Form", type="primary", key="select_guided_form_mode"):
            st.session_state.intake_mode = GUIDED_FORM_MODE
            st.rerun()

    with col2:
        st.markdown(
            """
            <div class="fs-card">
                <div class="fs-card-icon">✍️</div>
                <div class="fs-card-title">Write your project</div>
                <div class="fs-card-copy">
                    Describe the project naturally. FenceScope will extract useful
                    estimate details and ask only what is missing.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Write Description", type="primary", key="select_description_mode"):
            st.session_state.intake_mode = DESCRIPTION_MODE
            st.rerun()

    with col3:
        st.markdown(
            """
            <div class="fs-card">
                <div class="fs-card-icon">🎙️</div>
                <div class="fs-card-title">Talk about it</div>
                <div class="fs-card-copy">
                    Speak like you would on a phone call. FenceScope transcribes your
                    voice and lets you review the text.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Use Microphone", type="primary", key="select_voice_mode"):
            st.session_state.intake_mode = VOICE_MODE
            st.rerun()

    return None