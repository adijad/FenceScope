# ui/workflows/guided_review.py

import requests
import streamlit as st

from ui.api_client import (
    generate_estimate,
    run_missing_questions,
    run_precheck,
    send_customer_summary_email_request,
)
from ui.components.compliance import (
    render_compliance_report,
    render_failed_compliance_guidance,
)
from ui.components.estimate_summary import render_estimate_summary
from ui.components.questions import render_typed_question_input
from ui.state import (
    add_workflow_log,
    reset_guided_review_state,
)


def _error_response_text(error: Exception) -> str:
    response = getattr(error, "response", None)

    if response is not None:
        try:
            return response.text
        except Exception:
            return ""

    return ""


def render_workflow_trace():
    stage = st.session_state.workflow_stage

    progress_items = [
        ("validate", "Project details captured"),
        ("compliance", "Local fence code pre-check"),
        ("questions", "Missing information review"),
        ("estimate", "Estimate generation"),
        ("save", "Save for admin review"),
    ]

    completed_by_stage = {
        "idle": [],
        "running_compliance": ["validate"],
        "compliance_failed": ["validate", "compliance"],
        "generating_questions": ["validate", "compliance"],
        "answering_questions": ["validate", "compliance", "questions"],
        "ready_to_estimate": ["validate", "compliance", "questions"],
        "generating_estimate": ["validate", "compliance", "questions"],
        "estimate_complete": ["validate", "compliance", "questions", "estimate", "save"],
        "error": [],
    }

    active_by_stage = {
        "running_compliance": "compliance",
        "generating_questions": "questions",
        "answering_questions": "questions",
        "ready_to_estimate": "estimate",
        "generating_estimate": "estimate",
    }

    completed = completed_by_stage.get(stage, [])
    active = active_by_stage.get(stage)

    st.markdown("#### Review Progress")

    for key, label in progress_items:
        if key in completed:
            st.markdown(f"✅ {label}")
        elif key == active:
            st.markdown(f"⏳ {label}")
        else:
            st.markdown(f"○ {label}")

    if st.session_state.workflow_logs:
        with st.expander("Operational trace", expanded=True):
            for log in st.session_state.workflow_logs:
                st.write(log)


def validate_required_inputs(payload):
    missing = []

    if not payload.get("customer_name"):
        missing.append("Customer name")

    if not payload.get("customer_email"):
        missing.append("Email address")

    if not payload.get("customer_phone"):
        missing.append("Phone number")

    if not payload.get("address"):
        missing.append("Property address")

    if not payload.get("linear_feet") or payload.get("linear_feet") <= 0:
        missing.append("Fence length")

    if not payload.get("yard_sections"):
        missing.append("At least one yard section")

    return missing


def start_guided_review(payload, customer_notes, skip_missing_questions=False):
    reset_guided_review_state()

    missing_required = validate_required_inputs(payload)

    if missing_required:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = (
            "Please complete these fields before starting: "
            + ", ".join(missing_required)
        )
        return

    st.session_state.workflow_stage = "running_compliance"
    add_workflow_log("Project details captured.")
    add_workflow_log("Running local fence code pre-check.")

    try:
        report = run_precheck(payload)
    except requests.exceptions.RequestException as error:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = f"Could not connect to compliance pre-check: {error}"

        error_text = _error_response_text(error)
        if error_text:
            add_workflow_log(error_text)

        return

    st.session_state.compliance_report = report
    st.session_state.compliance_checked = True
    st.session_state.compliance_passed_or_review = report["overall"] != "FAIL"

    jurisdiction = report.get("jurisdiction") or "unknown jurisdiction"
    add_workflow_log(f"Compliance result: {report['overall']} for {jurisdiction}.")

    if report["overall"] == "FAIL":
        st.session_state.workflow_stage = "compliance_failed"
        add_workflow_log("Estimate generation blocked because compliance failed.")
        return

    if skip_missing_questions:
        st.session_state.questions_checked = True
        st.session_state.missing_questions = []
        add_workflow_log(
            "Description intake already collected follow-up answers. "
            "Skipping duplicate customer questionnaire."
        )
        finalize_guided_estimate(payload, customer_notes)
        return

    st.session_state.workflow_stage = "generating_questions"
    add_workflow_log("Checking project details for missing customer information.")

    try:
        question_data = run_missing_questions(payload)
    except requests.exceptions.RequestException as error:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = f"Could not connect to questions endpoint: {error}"

        error_text = _error_response_text(error)
        if error_text:
            add_workflow_log(error_text)

        return

    st.session_state.questions_checked = True
    st.session_state.missing_questions = question_data.get("missing_questions", [])
    st.session_state.question_risk_flags = question_data.get("risk_flags", [])
    st.session_state.question_confidence_score = question_data.get("confidence_score")
    st.session_state.missing_answers = {}
    st.session_state.current_question_index = 0

    question_count = len(st.session_state.missing_questions)
    add_workflow_log(f"Found {question_count} customer question(s) to confirm.")

    if question_count == 0:
        add_workflow_log("No missing questions found. Generating estimate.")
        finalize_guided_estimate(payload, customer_notes)
        return

    st.session_state.workflow_stage = "answering_questions"


def finalize_guided_estimate(payload, customer_notes):
    st.session_state.workflow_stage = "generating_estimate"
    add_workflow_log("Preparing final estimate payload.")

    answered_questions_text = "\n".join(
        [
            f"{question}: {answer}"
            for question, answer in st.session_state.missing_answers.items()
            if answer and str(answer).strip()
        ]
    )

    final_payload = payload.copy()

    if answered_questions_text:
        final_payload["customer_notes"] = (
            f"{customer_notes}\n\nAdditional customer answers:\n"
            f"{answered_questions_text}"
        )

    final_payload["missing_answers"] = st.session_state.missing_answers

    add_workflow_log("Running pricing, risk review, proposal generation, and database save.")

    try:
        result = generate_estimate(final_payload)
    except requests.exceptions.RequestException as error:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = "Estimate could not be generated."

        error_text = _error_response_text(error)
        if error_text:
            add_workflow_log(error_text)
        else:
            add_workflow_log(str(error))

        return

    st.session_state.estimate_result = result
    st.session_state.latest_saved_customer = {
        "id": result.get("customer_id"),
        "name": payload.get("customer_name"),
        "email": payload.get("customer_email"),
        "phone": payload.get("customer_phone"),
        "address": payload.get("address"),
    }

    st.session_state.workflow_stage = "estimate_complete"
    add_workflow_log(f"Estimate saved with ID: {result.get('estimate_id')}.")
    add_workflow_log("Admin review record is ready.")


def send_customer_summary_email(result, customer_email, customer_name, compliance_report):
    if not customer_email:
        st.error("Customer email is missing.")
        return

    email_payload = {
        "to_email": customer_email,
        "customer_name": customer_name,
        "address": result.get("address"),
        "estimate_id": result.get("estimate_id"),
        "estimated_total": result.get("estimated_total"),
        "low_range": result.get("low_range"),
        "high_range": result.get("high_range"),
        "status": result.get("status"),
        "confidence_score": result.get("confidence_score"),
        "compliance_overall": (compliance_report or {}).get("overall"),
        "compliance_jurisdiction": (compliance_report or {}).get("jurisdiction"),
        "remaining_questions": result.get("missing_questions", []),
    }

    with st.spinner("Sending estimate summary email..."):
        try:
            data = send_customer_summary_email_request(email_payload)
        except requests.exceptions.RequestException as error:
            st.error(f"Could not send email: {error}")

            error_text = _error_response_text(error)
            if error_text:
                st.code(error_text)

            return

    st.session_state.email_sent = True
    st.session_state.email_result = data

    st.success(f"Estimate summary sent to {customer_email}.")


def render_single_question_card(payload, customer_notes):
    questions = st.session_state.missing_questions
    idx = st.session_state.current_question_index

    if not questions:
        st.success("No missing questions. Preparing estimate.")

        if st.button("Generate Estimate", type="primary"):
            with st.spinner("Generating estimate..."):
                finalize_guided_estimate(payload, customer_notes)
            st.rerun()

        return

    total = len(questions)
    question = questions[idx]

    st.markdown(f"### Question {idx + 1} of {total}")

    progress_ratio = (idx + 1) / total
    st.progress(progress_ratio)

    with st.container(border=True):
        answer = render_typed_question_input(question, idx)
        st.session_state.missing_answers[question] = answer

    answered_count = sum(
        1
        for value in st.session_state.missing_answers.values()
        if value and str(value).strip()
    )

    st.caption(f"Answered {answered_count} of {total} required questions.")

    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 2])

    with nav_col1:
        if st.button("Back", disabled=idx == 0):
            st.session_state.current_question_index = max(0, idx - 1)
            st.rerun()

    with nav_col2:
        if idx < total - 1:
            if st.button("Next", type="primary"):
                if not answer or not str(answer).strip():
                    st.warning("Please answer this question before continuing.")
                else:
                    st.session_state.current_question_index = idx + 1
                    st.rerun()
        else:
            if st.button("Done", type="primary"):
                if not answer or not str(answer).strip():
                    st.warning("Please answer this question before generating the estimate.")
                else:
                    add_workflow_log("Questionnaire completed.")

                    with st.spinner("Generating estimate..."):
                        finalize_guided_estimate(payload, customer_notes)

                    st.rerun()

    with nav_col3:
        st.caption("Your answers help the estimator avoid quoting with missing project details.")


def render_guided_estimate_workflow(
    payload,
    customer_notes,
    skip_missing_questions=False,
    section_title="4. Guided Estimate Review",
    intro_copy=None,
    start_button_label="Start Estimate Review",
):
    st.subheader(section_title)

    with st.container(border=True):
        stage = st.session_state.workflow_stage

        if stage == "idle":
            st.markdown("### Ready to continue?")

            if intro_copy:
                st.write(intro_copy)
            else:
                st.write(
                    "FenceScope will check local fence-code rules across the selected yard sections, "
                    "collect any missing details, generate the estimate, and save it for admin review."
                )

            if st.button(start_button_label, type="primary"):
                with st.spinner("Starting estimate review..."):
                    start_guided_review(
                        payload,
                        customer_notes,
                        skip_missing_questions=skip_missing_questions,
                    )
                st.rerun()

            return

        render_workflow_trace()

        st.divider()

        if stage == "error":
            st.error(st.session_state.workflow_error or "Something went wrong.")

            if st.button("Restart Review"):
                reset_guided_review_state()
                st.rerun()

            return

        if stage == "compliance_failed":
            render_compliance_report(st.session_state.compliance_report)
            render_failed_compliance_guidance(st.session_state.compliance_report)

            if st.button("Edit Details and Restart Review"):
                reset_guided_review_state()
                st.rerun()

            return

        if stage == "answering_questions":
            render_single_question_card(payload, customer_notes)
            return

        if stage == "generating_estimate":
            st.info("Generating estimate...")
            return

        if stage == "estimate_complete":
            st.success("Estimate ready.")

            render_estimate_summary(
                result=st.session_state.estimate_result,
                payload=payload,
                compliance_report=st.session_state.compliance_report,
            )

            st.divider()

            st.subheader("Email Summary")

            if st.session_state.email_sent:
                st.success(
                    f"Estimate summary email sent to {payload.get('customer_email')}."
                )
            else:
                st.write(
                    "Send a customer-safe summary of this preliminary estimate to the email address provided above."
                )

                if st.button("Email Me This Estimate Summary", type="primary"):
                    send_customer_summary_email(
                        result=st.session_state.estimate_result,
                        customer_email=payload.get("customer_email"),
                        customer_name=payload.get("customer_name"),
                        compliance_report=st.session_state.compliance_report,
                    )
                    st.rerun()

            restart_col1, restart_col2 = st.columns([1, 3])

            with restart_col1:
                if st.button("Start New Review"):
                    reset_guided_review_state()
                    st.rerun()

            with restart_col2:
                st.caption(
                    "This estimate has been saved for admin review. Final quote approval remains with the estimating team."
                )

            return

        if stage in ["running_compliance", "generating_questions", "ready_to_estimate"]:
            st.info("Workflow is running. Please wait.")