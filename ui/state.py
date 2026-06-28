# ui/state.py

import streamlit as st


def initialize_session_state():
    """
    Initializes all Streamlit session state used by the customer estimate workflow.

    This is intentionally frontend-only. It does not call the backend.
    """

    # Property/address defaults
    if "selected_address" not in st.session_state:
        st.session_state.selected_address = ""

    if "map_lat" not in st.session_state:
        st.session_state.map_lat = 37.2296

    if "map_lng" not in st.session_state:
        st.session_state.map_lng = -80.4139

    if "address_prediction_map" not in st.session_state:
        st.session_state.address_prediction_map = {}

    if "last_selected_prediction" not in st.session_state:
        st.session_state.last_selected_prediction = None

    # Compliance/review state
    if "compliance_report" not in st.session_state:
        st.session_state.compliance_report = None

    if "compliance_checked" not in st.session_state:
        st.session_state.compliance_checked = False

    if "compliance_passed_or_review" not in st.session_state:
        st.session_state.compliance_passed_or_review = False

    # Estimate result state
    if "estimate_result" not in st.session_state:
        st.session_state.estimate_result = None

    if "last_payload_fingerprint" not in st.session_state:
        st.session_state.last_payload_fingerprint = None

    if "latest_saved_customer" not in st.session_state:
        st.session_state.latest_saved_customer = None

    # Missing-question state used by the existing estimate review workflow
    if "questions_checked" not in st.session_state:
        st.session_state.questions_checked = False

    if "missing_questions" not in st.session_state:
        st.session_state.missing_questions = []

    if "missing_answers" not in st.session_state:
        st.session_state.missing_answers = {}

    if "question_risk_flags" not in st.session_state:
        st.session_state.question_risk_flags = []

    if "question_confidence_score" not in st.session_state:
        st.session_state.question_confidence_score = None

    if "current_question_index" not in st.session_state:
        st.session_state.current_question_index = 0

    # Workflow trace state
    if "workflow_stage" not in st.session_state:
        st.session_state.workflow_stage = "idle"

    if "workflow_logs" not in st.session_state:
        st.session_state.workflow_logs = []

    if "workflow_error" not in st.session_state:
        st.session_state.workflow_error = None

    # Email state
    if "email_sent" not in st.session_state:
        st.session_state.email_sent = False

    if "email_result" not in st.session_state:
        st.session_state.email_result = None

    # User-intake state
    if "user_started" not in st.session_state:
        st.session_state.user_started = False

    if "intake_mode" not in st.session_state:
        st.session_state.intake_mode = None

    if "raw_project_description" not in st.session_state:
        st.session_state.raw_project_description = ""

    if "intake_analysis" not in st.session_state:
        st.session_state.intake_analysis = None

    if "prefilled_fields" not in st.session_state:
        st.session_state.prefilled_fields = {}

    # Description-intake staged flow
    if "description_stage" not in st.session_state:
        st.session_state.description_stage = "idle"

    if "description_missing_questions" not in st.session_state:
        st.session_state.description_missing_questions = []

    if "description_missing_answers" not in st.session_state:
        st.session_state.description_missing_answers = {}

    if "description_current_question_index" not in st.session_state:
        st.session_state.description_current_question_index = 0

    if "description_analysis_error" not in st.session_state:
        st.session_state.description_analysis_error = None

    if "guided_form_prefill_applied" not in st.session_state:
        st.session_state.guided_form_prefill_applied = False


def reset_workflow_state():
    """
    Resets the estimate workflow whenever core project details change.
    Does not reset selected address or map center.
    """

    st.session_state.compliance_report = None
    st.session_state.compliance_checked = False
    st.session_state.compliance_passed_or_review = False
    st.session_state.estimate_result = None
    st.session_state.latest_saved_customer = None

    st.session_state.questions_checked = False
    st.session_state.missing_questions = []
    st.session_state.missing_answers = {}
    st.session_state.question_risk_flags = []
    st.session_state.question_confidence_score = None

    st.session_state.workflow_stage = "idle"
    st.session_state.workflow_logs = []
    st.session_state.workflow_error = None
    st.session_state.current_question_index = 0

    st.session_state.email_sent = False
    st.session_state.email_result = None


def reset_guided_review_state():
    """
    Resets only the guided review workflow.
    """

    st.session_state.compliance_report = None
    st.session_state.compliance_checked = False
    st.session_state.compliance_passed_or_review = False
    st.session_state.estimate_result = None
    st.session_state.latest_saved_customer = None

    st.session_state.questions_checked = False
    st.session_state.missing_questions = []
    st.session_state.missing_answers = {}
    st.session_state.question_risk_flags = []
    st.session_state.question_confidence_score = None

    st.session_state.workflow_stage = "idle"
    st.session_state.workflow_logs = []
    st.session_state.workflow_error = None
    st.session_state.current_question_index = 0

    st.session_state.email_sent = False
    st.session_state.email_result = None


def reset_description_intake_state():
    """
    Resets only the description-intake flow.
    """

    st.session_state.description_stage = "idle"
    st.session_state.intake_analysis = None
    st.session_state.description_missing_questions = []
    st.session_state.description_missing_answers = {}
    st.session_state.description_current_question_index = 0
    st.session_state.description_analysis_error = None
    st.session_state.prefilled_fields = {}
    st.session_state.guided_form_prefill_applied = False


def reset_intake_state():
    """
    Resets the full intake branch state.
    """

    st.session_state.intake_mode = None
    st.session_state.raw_project_description = ""
    reset_description_intake_state()


def add_workflow_log(message: str):
    if "workflow_logs" not in st.session_state:
        st.session_state.workflow_logs = []

    st.session_state.workflow_logs.append(message)