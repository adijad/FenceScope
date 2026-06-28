# ui/components/voice_intake.py

import requests
import streamlit as st

from ui.api_client import transcribe_audio_intake_request
from ui.components.description_intake import (
    run_description_intake_analysis,
    render_description_question_flow,
    render_not_relevant_result,
    render_review_details,
)
from ui.state import reset_description_intake_state, reset_guided_review_state
from ui.theme import render_workflow_pipeline


def reset_voice_intake_state():
    st.session_state.voice_transcript = ""
    st.session_state.voice_transcription_error = None
    reset_description_intake_state()
    reset_guided_review_state()


def render_voice_guidance():
    with st.container(border=True):
        st.markdown("### What to say")
        st.write(
            "Describe the project the way you would on a phone call. Mention the fence type, "
            "height, yard area, approximate length, gates, old fence removal, slope, access, "
            "pets, pool, HOA, property-line concerns, and timeline if you know them."
        )

        st.caption(
            "Example: I want a 6 foot wood privacy fence around my backyard. We need one "
            "walk gate near the driveway, there is an old chain-link fence to remove, and "
            "the backyard has a slight slope."
        )


def render_recording_panel():
    with st.container(border=True):
        st.markdown("### Step 1: Record your project details")

        st.caption(
            "Use your microphone to describe the fence project. After recording, FenceScope "
            "will transcribe it and show you the text before analysis."
        )

        audio_value = st.audio_input(
            "Tell us what kind of fence project you need",
            key="voice_project_audio",
        )

        if not audio_value:
            st.info("Record your project details to continue.")
            return

        st.caption("Recording captured. Click the button below to transcribe it.")

        if st.button(
            "Transcribe Recording",
            type="primary",
            key="transcribe_voice_recording",
        ):
            with st.status("Transcribing your project details...", expanded=True) as status:
                try:
                    st.write("Reading microphone recording...")
                    result = transcribe_audio_intake_request(audio_value)

                    transcript = result.get("transcript", "")

                    if not transcript.strip():
                        st.session_state.voice_transcription_error = (
                            "The transcription came back empty. Please try recording again."
                        )
                        st.error(st.session_state.voice_transcription_error)

                        status.update(
                            label="Transcription failed.",
                            state="error",
                        )
                        return

                    st.session_state.voice_transcript = transcript
                    st.session_state.raw_project_description = transcript
                    st.session_state.voice_transcription_error = None

                    st.write("Transcript created.")
                    status.update(
                        label="Transcription complete.",
                        state="complete",
                    )

                    st.rerun()

                except requests.exceptions.RequestException as error:
                    st.session_state.voice_transcription_error = str(error)

                    st.error(f"Could not transcribe recording: {error}")

                    response = getattr(error, "response", None)
                    if response is not None:
                        try:
                            st.code(response.text)
                        except Exception:
                            pass

                    status.update(
                        label="Transcription failed.",
                        state="error",
                    )


def render_transcript_review_panel(customer_property_context: dict):
    transcript_value = st.session_state.get("voice_transcript", "")

    if not transcript_value:
        return

    st.success("We transcribed your recording. Please review the text before continuing.")

    with st.container(border=True):
        st.markdown("### Review Your Project Description")

        edited_transcript = st.text_area(
            "Editable transcript",
            value=transcript_value,
            height=150,
            key="voice_transcript_text_area",
            label_visibility="collapsed",
        )

        st.session_state.voice_transcript = edited_transcript
        st.session_state.raw_project_description = edited_transcript

        word_count = len(edited_transcript.split()) if edited_transcript else 0
        st.caption(f"Transcript length: {word_count} words")

        action_col1, action_col2 = st.columns([1, 1])

        with action_col1:
            if st.button(
                "Analyze Project Details",
                type="primary",
                disabled=not edited_transcript.strip(),
                key="analyze_voice_description",
            ):
                run_description_intake_analysis(
                    customer_property_context=customer_property_context,
                    raw_description=edited_transcript,
                )
                st.rerun()

        with action_col2:
            if st.button("Record Again", key="voice_record_again"):
                reset_voice_intake_state()
                st.rerun()

        st.caption(
            "FenceScope will use this transcript to extract project details, "
            "ask missing questions, then run compliance and pricing."
        )

    render_workflow_pipeline("Voice intake workflow")

def render_voice_idle_entry(customer_property_context: dict):
    transcript_exists = bool(st.session_state.get("voice_transcript", "").strip())

    if not transcript_exists:
        render_voice_guidance()
        st.divider()
        render_recording_panel()
        return

    render_transcript_review_panel(customer_property_context)

    # with st.expander("Record a different message", expanded=False):
    #     render_recording_panel()


def render_voice_intake(customer_property_context: dict):
    st.subheader("Talk About Your Project")

    st.caption(
        "Use your microphone to describe the fence project. FenceScope will transcribe "
        "your recording, show you the text, ask only important missing questions, and then "
        "run the same estimate workflow."
    )

    stage = st.session_state.get("description_stage", "idle")

    if stage == "idle":
        render_voice_idle_entry(customer_property_context)
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

    st.warning("Unknown voice intake stage. Please start over.")
    st.session_state.description_stage = "idle"