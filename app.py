import json
import math
import re

import folium
import pandas as pd
import requests
import streamlit as st

from folium.plugins import Draw
from streamlit_folium import st_folium
from streamlit_searchbox import st_searchbox

from backend.database import init_db
from backend.storage import get_all_customers


API_URL = "http://127.0.0.1:8000/estimate"
PRECHECK_URL = "http://127.0.0.1:8000/precheck"
QUESTIONS_URL = "http://127.0.0.1:8000/questions"
ESTIMATES_URL = "http://127.0.0.1:8000/estimates"
ADDRESS_AUTOCOMPLETE_URL = "http://127.0.0.1:8000/address/autocomplete"
ADDRESS_PLACE_URL = "http://127.0.0.1:8000/address/place"
EMAIL_SUMMARY_URL = "http://127.0.0.1:8000/email/estimate-summary"


# ---------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------

def haversine_feet(lat1, lon1, lat2, lon2):
    earth_radius_feet = 20925524.9

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_feet * c


def calculate_path_feet(coordinates):
    """
    GeoJSON coordinates come in [longitude, latitude] order.
    """
    if not coordinates or len(coordinates) < 2:
        return 0.0

    total_feet = 0.0

    for i in range(len(coordinates) - 1):
        lon1, lat1 = coordinates[i]
        lon2, lat2 = coordinates[i + 1]

        total_feet += haversine_feet(lat1, lon1, lat2, lon2)

    return round(total_feet, 2)


def extract_drawn_measurement_feet(map_data):
    if not map_data:
        return None

    drawings = map_data.get("all_drawings") or []

    if not drawings:
        return None

    latest_drawing = drawings[-1]
    geometry = latest_drawing.get("geometry", {})
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "LineString":
        return calculate_path_feet(coordinates)

    if geometry_type == "Polygon":
        outer_ring = coordinates[0]
        return calculate_path_feet(outer_ring)

    return None


# ---------------------------------------------------------
# Address lookup helpers
# ---------------------------------------------------------

def autocomplete_address_options(search_term: str):
    if not search_term or len(search_term.strip()) < 2:
        return []

    try:
        response = requests.get(
            ADDRESS_AUTOCOMPLETE_URL,
            params={"q": search_term},
            timeout=10,
        )
        response.raise_for_status()

        predictions = response.json().get("predictions", [])

        st.session_state.address_prediction_map = {
            prediction["description"]: prediction
            for prediction in predictions
        }

        return [prediction["description"] for prediction in predictions]

    except requests.exceptions.RequestException as error:
        st.warning(f"Address autocomplete failed: {error}")
        return []


def load_selected_place(selected_prediction: str):
    prediction = st.session_state.address_prediction_map.get(selected_prediction)

    if not prediction:
        return

    place_id = prediction["place_id"]

    try:
        response = requests.get(
            ADDRESS_PLACE_URL,
            params={"place_id": place_id},
            timeout=10,
        )
        response.raise_for_status()

        place = response.json().get("place")

        if not place:
            return

        st.session_state.selected_address = place["display_name"]
        st.session_state.map_lat = place["lat"]
        st.session_state.map_lng = place["lng"]

    except requests.exceptions.RequestException as error:
        st.error(f"Could not load selected place: {error}")


# ---------------------------------------------------------
# Session state
# ---------------------------------------------------------

def initialize_session_state():
    if "selected_address" not in st.session_state:
        st.session_state.selected_address = "888 Patrick Henry Dr, Blacksburg, VA 24060, USA"

    if "map_lat" not in st.session_state:
        st.session_state.map_lat = 37.2296

    if "map_lng" not in st.session_state:
        st.session_state.map_lng = -80.4139

    if "address_prediction_map" not in st.session_state:
        st.session_state.address_prediction_map = {}

    if "last_selected_prediction" not in st.session_state:
        st.session_state.last_selected_prediction = None

    if "compliance_report" not in st.session_state:
        st.session_state.compliance_report = None

    if "compliance_checked" not in st.session_state:
        st.session_state.compliance_checked = False

    if "compliance_passed_or_review" not in st.session_state:
        st.session_state.compliance_passed_or_review = False

    if "estimate_result" not in st.session_state:
        st.session_state.estimate_result = None

    if "last_payload_fingerprint" not in st.session_state:
        st.session_state.last_payload_fingerprint = None

    if "latest_saved_customer" not in st.session_state:
        st.session_state.latest_saved_customer = None

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

    if "workflow_stage" not in st.session_state:
        st.session_state.workflow_stage = "idle"

    if "workflow_logs" not in st.session_state:
        st.session_state.workflow_logs = []

    if "workflow_error" not in st.session_state:
        st.session_state.workflow_error = None

    if "current_question_index" not in st.session_state:
        st.session_state.current_question_index = 0

    if "email_sent" not in st.session_state:
        st.session_state.email_sent = False

    if "email_result" not in st.session_state:
        st.session_state.email_result = None


def reset_workflow_state():
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


def reset_guided_review_state():
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


def add_workflow_log(message: str):
    st.session_state.workflow_logs.append(message)


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------

def render_sidebar():
    with st.sidebar:
        st.header("Workflow")
        st.write(
            """
            1. Capture customer details  
            2. Select property address  
            3. Draw or enter fence measurement  
            4. Start guided estimate review  
            5. Run compliance pre-check  
            6. Answer missing questions  
            7. Generate estimate  
            8. Save estimate for admin review
            """
        )

        st.divider()

        st.subheader("System Design")
        st.write(
            """
            **Address autocomplete:** Finds property location  
            **Map:** Measures linear footage  
            **Compliance agent:** Checks local fence code first  
            **Question agent:** Finds missing customer details before estimate  
            **Pricing engine:** Calculates price deterministically  
            **Risk agent:** Reviews risks and missing info  
            **Proposal agent:** Drafts internal proposal copy  
            **Postgres:** Stores full estimate history  
            **Human review:** Controls final action
            """
        )

        st.divider()

        st.caption(
            "Prototype role switcher. In production, this would use authentication, permissions, and audit logs."
        )


# ---------------------------------------------------------
# Shared rendering helpers
# ---------------------------------------------------------

def render_compliance_report(report):
    if not report:
        st.info("No compliance report available.")
        return

    verdict = report.get("overall", "NEEDS_REVIEW")
    jurisdiction = report.get("jurisdiction") or "jurisdiction not covered"

    if verdict == "PASS":
        st.success(f"Compliance: {verdict} - {jurisdiction}")
    elif verdict == "FAIL":
        st.error(f"Compliance: {verdict} - {jurisdiction}")
    else:
        st.warning(f"Compliance: {verdict} - {jurisdiction}")

    if report.get("summary"):
        st.write(report["summary"])

    for finding in report.get("findings", []):
        icon = {
            "pass": "✅",
            "fail": "❌",
            "needs_review": "⚠️",
        }.get(finding.get("status"), "⚠️")

        with st.expander(
            f"{icon} {finding.get('rule_id', 'rule')}  "
            f"(confidence {finding.get('confidence', 'N/A')})"
        ):
            st.write(finding.get("explanation", "No explanation provided."))

            if finding.get("verbatim_text"):
                st.markdown(f"> {finding['verbatim_text']}")

            if finding.get("source_url"):
                st.markdown(f"[View ordinance source]({finding['source_url']})")

    if report.get("disclaimer"):
        st.caption(report["disclaimer"])


def render_failed_compliance_guidance(report):
    failed_rule_ids = [
        finding["rule_id"]
        for finding in report.get("findings", [])
        if finding.get("status") == "fail"
    ]

    st.error(
        "This request cannot be estimated as entered. Please adjust the highlighted fields before generating an estimate."
    )

    if "fence-height-front-yard" in failed_rule_ids:
        st.warning(
            "Field to fix: Fence height. Front-yard fences in this jurisdiction cannot exceed four feet."
        )

    if "fence-location-sight-triangle" in failed_rule_ids:
        st.warning(
            "Field to review: Yard location. Front-yard or street-facing fences may affect visibility and sight-triangle rules."
        )

    if not failed_rule_ids:
        st.warning(
            "The compliance checker found a blocking issue. Review the selected fence height, yard location, material, and property address."
        )


def render_risk_flags(risk_flags):
    if not risk_flags:
        st.write("No major risks flagged.")
        return

    for risk in risk_flags:
        severity = risk.get("severity", "unknown").upper()
        risk_type = risk.get("risk_type", "risk").replace("_", " ").title()
        explanation = risk.get("explanation", "No explanation provided.")
        recommended_action = risk.get("recommended_action", "No recommended action provided.")

        st.markdown(
            f"""
            **{risk_type}**  
            Severity: `{severity}`  
            {explanation}  
            Recommended action: {recommended_action}
            """
        )


def render_line_items(line_items):
    if not line_items:
        st.info("No line items available.")
        return

    line_items_df = pd.DataFrame(line_items)
    st.dataframe(line_items_df, use_container_width=True)


def render_customer_answers(missing_answers):
    answered_items = {
        question: answer
        for question, answer in (missing_answers or {}).items()
        if answer and str(answer).strip()
    }

    if not answered_items:
        st.info("No additional customer answers captured for this estimate.")
        return

    for question, answer in answered_items.items():
        st.markdown(f"**Q:** {question}")
        st.markdown(f"**A:** {answer}")
        st.divider()


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
            response = requests.post(
                EMAIL_SUMMARY_URL,
                json=email_payload,
                timeout=60,
            )
        except requests.exceptions.RequestException as error:
            st.error(f"Could not connect to email endpoint: {error}")
            return

    if response.status_code != 200:
        st.error("Email could not be sent.")
        st.code(response.text)
        return

    data = response.json()

    st.session_state.email_sent = True
    st.session_state.email_result = data

    st.success(f"Estimate summary sent to {customer_email}.")

# ---------------------------------------------------------
# Typed question rendering
# ---------------------------------------------------------

def normalize_question_text(question: str) -> str:
    return question.strip().lower()


def question_key_from_text(question: str) -> str:
    q = normalize_question_text(question)

    if "hoa" in q:
        return "hoa_approval"

    if "pet" in q or "dog" in q:
        return "pet_containment"

    if "timeline" in q or "desired installation" in q or "schedule" in q:
        return "timeline"

    if "material" in q and ("existing fence" in q or "old fence" in q):
        return "existing_fence_material"

    if "condition" in q and ("old" in q or "existing" in q or "chain link" in q):
        return "old_fence_condition_length"

    if "slope" in q or "grade" in q:
        return "slope_details"

    if "property line" in q or "neighbor" in q or "shared fence" in q:
        return "property_line_uncertainty"

    if "access" in q:
        return "access_details"

    if "gate" in q:
        return "gate_details"

    return "free_text"


def stable_question_suffix(question: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", question.strip().lower())
    return cleaned[:50]


def render_typed_question_input(question: str, idx: int) -> str:
    question_key = question_key_from_text(question)
    question_suffix = stable_question_suffix(question)
    base_key = f"typed_question_{idx}_{question_key}_{question_suffix}"

    st.markdown(f"**{question}**")

    if question_key == "hoa_approval":
        answer = st.selectbox(
            "HOA approval status",
            [
                "Select an option",
                "Yes, HOA approval has been obtained",
                "No, HOA approval has not been obtained",
                "Not sure / customer needs to check",
                "No HOA applies to this property",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "pet_containment":
        primary = st.selectbox(
            "Is this fence intended for pet containment?",
            [
                "Select an option",
                "Yes, mainly for pet containment",
                "Partially, pets are one reason",
                "No, not for pet containment",
            ],
            key=f"{base_key}_select",
        )

        details = st.text_input(
            "Optional pet details",
            placeholder="Example: two dogs, small dog gap concerns, gate latch concerns",
            key=f"{base_key}_details",
        )

        if primary == "Select an option":
            return ""

        if details.strip():
            return f"{primary}. Details: {details.strip()}"

        return primary

    if question_key == "timeline":
        answer = st.selectbox(
            "Desired installation timeline",
            [
                "Select an option",
                "ASAP",
                "Within 1 to 2 weeks",
                "Within 2 to 4 weeks",
                "Within 1 to 2 months",
                "Flexible / no rush",
                "Customer is not sure yet",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "existing_fence_material":
        material = st.selectbox(
            "Existing fence material",
            [
                "Select an option",
                "Chain link",
                "Wood",
                "Vinyl",
                "Aluminum",
                "Split rail",
                "Mixed materials",
                "Not sure",
                "No existing fence",
            ],
            key=f"{base_key}_material",
        )

        condition = st.selectbox(
            "Existing fence condition",
            [
                "Select an option",
                "Good condition",
                "Partially damaged",
                "Heavily damaged",
                "Partially removed already",
                "Fully standing",
                "Not sure",
                "Not applicable",
            ],
            key=f"{base_key}_condition",
        )

        if material == "Select an option" or condition == "Select an option":
            return ""

        return f"Existing fence material: {material}. Condition: {condition}."

    if question_key == "old_fence_condition_length":
        condition = st.selectbox(
            "Old fence condition",
            [
                "Select an option",
                "Good condition",
                "Partially damaged",
                "Heavily damaged",
                "Partially removed already",
                "Fully standing",
                "Not sure",
            ],
            key=f"{base_key}_condition",
        )

        old_fence_length = st.number_input(
            "Approximate old fence length to remove",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"{base_key}_length",
        )

        if condition == "Select an option":
            return ""

        if old_fence_length <= 0:
            return f"Old fence condition: {condition}. Old fence length: not sure."

        return (
            f"Old fence condition: {condition}. "
            f"Approximate removal length: {old_fence_length:.0f} linear feet."
        )

    if question_key == "slope_details":
        slope_level = st.selectbox(
            "Slope severity",
            [
                "Select an option",
                "Slight slope",
                "Moderate slope",
                "Steep slope",
                "Mixed slope across yard",
                "Not sure",
            ],
            key=f"{base_key}_slope_level",
        )

        slope_uniformity = st.selectbox(
            "Slope pattern",
            [
                "Select an option",
                "Mostly uniform",
                "Varies across the fence line",
                "Only one section is sloped",
                "Not sure",
            ],
            key=f"{base_key}_slope_pattern",
        )

        details = st.text_input(
            "Optional slope details",
            placeholder="Example: backyard slopes down toward the street",
            key=f"{base_key}_details",
        )

        if slope_level == "Select an option" or slope_uniformity == "Select an option":
            return ""

        answer = f"Slope severity: {slope_level}. Slope pattern: {slope_uniformity}."

        if details.strip():
            answer += f" Details: {details.strip()}"

        return answer

    if question_key == "property_line_uncertainty":
        answer = st.selectbox(
            "Property line or neighbor uncertainty",
            [
                "Select an option",
                "No known property line uncertainty",
                "Customer is not sure about property line",
                "Fence may be shared with neighbor",
                "Survey may be needed",
                "Neighbor approval may be needed",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "access_details":
        answer = st.selectbox(
            "Crew access to fence area",
            [
                "Select an option",
                "Clear access",
                "Narrow gate access",
                "No vehicle access",
                "Steep or difficult access",
                "Obstructions may need removal",
                "Not sure",
            ],
            key=f"{base_key}_select",
        )

        if answer == "Select an option":
            return ""

        return answer

    if question_key == "gate_details":
        answer = st.text_input(
            "Gate details",
            placeholder="Example: one 4 ft walk gate on left side, one double gate near driveway",
            key=f"{base_key}_text",
        )

        return answer.strip()

    answer = st.text_input(
        "Answer",
        key=f"{base_key}_text",
    )

    return answer.strip()


# ---------------------------------------------------------
# Guided workflow engine
# ---------------------------------------------------------

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

    return missing


def start_guided_review(payload, customer_notes):
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
        precheck_response = requests.post(PRECHECK_URL, json=payload, timeout=60)
    except requests.exceptions.RequestException as error:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = f"Could not connect to compliance pre-check: {error}"
        return

    if precheck_response.status_code != 200:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = "Compliance pre-check returned an error."
        add_workflow_log(precheck_response.text)
        return

    report = precheck_response.json()

    st.session_state.compliance_report = report
    st.session_state.compliance_checked = True
    st.session_state.compliance_passed_or_review = report["overall"] != "FAIL"

    jurisdiction = report.get("jurisdiction") or "unknown jurisdiction"
    add_workflow_log(f"Compliance result: {report['overall']} for {jurisdiction}.")

    if report["overall"] == "FAIL":
        st.session_state.workflow_stage = "compliance_failed"
        add_workflow_log("Estimate generation blocked because compliance failed.")
        return

    st.session_state.workflow_stage = "generating_questions"
    add_workflow_log("Checking project details for missing customer information.")

    try:
        questions_response = requests.post(QUESTIONS_URL, json=payload, timeout=60)
    except requests.exceptions.RequestException as error:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = f"Could not connect to questions endpoint: {error}"
        return

    if questions_response.status_code != 200:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = "Missing question check returned an error."
        add_workflow_log(questions_response.text)
        return

    question_data = questions_response.json()

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
        response = requests.post(API_URL, json=final_payload, timeout=90)
    except requests.exceptions.RequestException as error:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = f"Could not connect to backend: {error}"
        return

    if response.status_code != 200:
        st.session_state.workflow_stage = "error"
        st.session_state.workflow_error = "Estimate could not be generated."
        add_workflow_log(response.text)
        return

    result = response.json()

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


def render_guided_estimate_workflow(payload, customer_notes):
    st.subheader("4. Guided Estimate Review")

    with st.container(border=True):
        stage = st.session_state.workflow_stage

        if stage == "idle":
            st.markdown("### Ready to review your fence project?")
            st.write(
                "FenceScope will check local fence-code rules, collect any missing details, "
                "generate the estimate, and save it for admin review."
            )

            if st.button("Start Estimate Review", type="primary"):
                with st.spinner("Starting estimate review..."):
                    start_guided_review(payload, customer_notes)
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
            render_estimate_summary(st.session_state.estimate_result)

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
                    "This estimate has been saved for admin review. The customer-facing proposal remains internal until reviewed."
                )

            return

        if stage in ["running_compliance", "generating_questions", "ready_to_estimate"]:
            st.info("Workflow is running. Please wait.")


# ---------------------------------------------------------
# Estimate summary
# ---------------------------------------------------------

def render_estimate_summary(result):
    if not result:
        st.info("No estimate result available.")
        return

    st.subheader("Estimate Summary")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        st.metric("Estimated Total", f"${result['estimated_total']:,.2f}")

    with metric_col2:
        st.metric("Low Range", f"${result['low_range']:,.2f}")

    with metric_col3:
        st.metric("High Range", f"${result['high_range']:,.2f}")

    with metric_col4:
        st.metric("Confidence", result["confidence_score"])

    status = result["status"].replace("_", " ").title()

    if result["status"] == "ready_to_send":
        st.success(f"Status: {status}")
    elif result["status"] in ["needs_customer_info", "needs_estimator_review"]:
        st.warning(f"Status: {status}")
    else:
        st.error(f"Status: {status}")

    if result.get("estimate_id"):
        st.caption(f"Saved estimate ID: {result['estimate_id']}")

    st.info(
        "This is a preliminary estimate. A representative will review the project details before a final quote is issued."
    )

    st.divider()

    left_col, right_col = st.columns([1, 1])

    with left_col:
        st.subheader("Line Items")
        render_line_items(result.get("line_items", []))

        st.subheader("Risk Flags")
        render_risk_flags(result.get("risk_flags", []))

    with right_col:
        st.subheader("Remaining Missing Questions")

        if result.get("missing_questions"):
            for question in result["missing_questions"]:
                st.write(f"- {question}")
        else:
            st.success("No remaining missing questions.")

    st.divider()

    st.subheader("Customer Next Step")
    st.write(
        "A representative will contact the customer to confirm any final details, review compliance requirements, and finalize the quote."
    )


# ---------------------------------------------------------
# User view
# ---------------------------------------------------------

def render_user_view():
    st.title("FenceScope AI")
    st.caption(
        "AI-assisted estimate triage and proposal workflow for residential fencing companies."
    )

    st.subheader("1. Customer Details")

    customer_col1, customer_col2, customer_col3 = st.columns(3)

    with customer_col1:
        customer_name = st.text_input("Customer name", "Sarah Miller")

    with customer_col2:
        customer_email = st.text_input("Email address", "sarah@example.com")

    with customer_col3:
        customer_phone = st.text_input("Phone number", "(540) 555-0198")

    st.divider()

    st.subheader("2. Property Details")

    selected_prediction = st_searchbox(
        search_function=autocomplete_address_options,
        placeholder="Start typing property address...",
        label="Search property address",
        key="property_address_autocomplete",
    )

    if selected_prediction and selected_prediction != st.session_state.last_selected_prediction:
        st.session_state.last_selected_prediction = selected_prediction
        load_selected_place(selected_prediction)
        reset_workflow_state()
        st.success("Address selected. Map center updated.")
        st.rerun()

    selected_address = st.session_state.selected_address
    property_lat = st.session_state.map_lat
    property_lng = st.session_state.map_lng

    st.write(f"**Selected property:** {selected_address}")
    st.write(f"**Map center:** {property_lat:.6f}, {property_lng:.6f}")

    job_col1, job_col2 = st.columns(2)

    with job_col1:
        fence_type = st.selectbox(
            "Fence type",
            [
                "wood_privacy",
                "vinyl_privacy",
                "chain_link",
                "aluminum",
                "split_rail",
            ],
            index=0,
        )

        yard_location_label = st.selectbox(
            "Yard location",
            [
                "Back yard",
                "Side yard",
                "Front yard",
            ],
            index=0,
            help="Used by the compliance agent because front, side, and back yards often have different fence rules.",
        )

        yard_location_map = {
            "Back yard": "back",
            "Side yard": "side",
            "Front yard": "front",
        }

        yard_location = yard_location_map[yard_location_label]

        height_ft = st.number_input(
            "Fence height",
            min_value=3,
            max_value=10,
            value=6,
            step=1,
        )

        manual_linear_feet = st.number_input(
            "Manual measured fence length fallback",
            min_value=1.0,
            value=186.0,
            step=1.0,
        )

    with job_col2:
        gate_count = st.number_input(
            "Walk gates",
            min_value=0,
            value=2,
            step=1,
        )

        double_gate_count = st.number_input(
            "Double gates",
            min_value=0,
            value=0,
            step=1,
        )

        old_fence_removal = st.checkbox("Old fence removal required", value=True)
        difficult_access = st.checkbox("Difficult access", value=False)
        slope_present = st.checkbox("Slope present", value=True)

    customer_notes = st.text_area(
        "Customer / property notes",
        value=(
            "Backyard slopes slightly. HOA neighborhood. We have two dogs and an old "
            "chain link fence that needs to be removed. Wants quote quickly."
        ),
        height=120,
    )

    st.divider()

    st.subheader("3. Map-Based Fence Measurement")
    st.caption(
        "Draw the proposed fence line on the satellite map. The app calculates total linear footage from the drawn path."
    )

    map_settings_col, map_col = st.columns([1, 3])

    with map_settings_col:
        st.write("Map controls")

        manual_map_lat = st.number_input(
            "Latitude",
            value=float(st.session_state.map_lat),
            format="%.6f",
        )

        manual_map_lng = st.number_input(
            "Longitude",
            value=float(st.session_state.map_lng),
            format="%.6f",
        )

        if st.button("Update Map Center Manually"):
            st.session_state.map_lat = manual_map_lat
            st.session_state.map_lng = manual_map_lng
            reset_workflow_state()
            st.rerun()

        st.caption(
            "Manual coordinates are a fallback. In production, Google Places Autocomplete and Place Details would handle this automatically."
        )

    with map_col:
        fence_map = folium.Map(
            location=[st.session_state.map_lat, st.session_state.map_lng],
            zoom_start=19,
            tiles=None,
        )

        folium.TileLayer(
            tiles=(
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ),
            attr="Esri World Imagery",
            name="Satellite",
            overlay=False,
            control=True,
        ).add_to(fence_map)

        folium.TileLayer(
            tiles="OpenStreetMap",
            name="Street Map",
            overlay=False,
            control=True,
        ).add_to(fence_map)

        Draw(
            export=False,
            draw_options={
                "polyline": True,
                "polygon": True,
                "rectangle": False,
                "circle": False,
                "marker": False,
                "circlemarker": False,
            },
            edit_options={
                "edit": True,
                "remove": True,
            },
        ).add_to(fence_map)

        folium.LayerControl().add_to(fence_map)

        map_data = st_folium(
            fence_map,
            width=900,
            height=500,
            returned_objects=["all_drawings"],
            key="fence_map",
        )

    drawn_feet = extract_drawn_measurement_feet(map_data)

    if drawn_feet and drawn_feet > 0:
        st.success(f"Measured fence length from map: {drawn_feet:,.2f} linear feet")
        use_map_measurement = st.checkbox(
            "Use map measurement for estimate",
            value=True,
        )
    else:
        st.info("Draw a polyline or polygon on the map to calculate fence length.")
        use_map_measurement = False

    final_linear_feet = (
        drawn_feet if use_map_measurement and drawn_feet else manual_linear_feet
    )

    st.write(f"**Linear feet used for estimate:** {final_linear_feet:,.2f}")

    st.divider()

    payload = {
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "address": selected_address,
        "property_lat": st.session_state.map_lat,
        "property_lng": st.session_state.map_lng,
        "fence_type": fence_type,
        "height_ft": height_ft,
        "linear_feet": final_linear_feet,
        "yard_location": yard_location,
        "gate_count": gate_count,
        "double_gate_count": double_gate_count,
        "old_fence_removal": old_fence_removal,
        "difficult_access": difficult_access,
        "slope_present": slope_present,
        "customer_notes": customer_notes,
    }

    payload_fingerprint = json.dumps(payload, sort_keys=True)

    if (
        st.session_state.last_payload_fingerprint is not None
        and st.session_state.last_payload_fingerprint != payload_fingerprint
    ):
        reset_workflow_state()
        st.session_state.last_payload_fingerprint = payload_fingerprint
        st.info("Project details changed. Start the estimate review again.")

    if st.session_state.last_payload_fingerprint is None:
        st.session_state.last_payload_fingerprint = payload_fingerprint

    render_guided_estimate_workflow(payload, customer_notes)




# ---------------------------------------------------------
# Admin view
# ---------------------------------------------------------

def fetch_saved_estimates():
    try:
        response = requests.get(ESTIMATES_URL, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as error:
        st.error(f"Could not load saved estimates from backend: {error}")
        return []


def render_estimate_detail(estimate, key_prefix):
    estimate_result = estimate.get("estimate_result") or {}
    compliance_report = estimate.get("compliance_report") or {}
    missing_answers = estimate.get("missing_answers") or {}

    st.subheader(f"Estimate #{estimate.get('id')}")

    meta_col1, meta_col2, meta_col3 = st.columns(3)

    with meta_col1:
        st.write(f"**Customer:** {estimate.get('customer_name', 'Unknown')}")
        st.write(f"**Email:** {estimate.get('customer_email', '')}")
        st.write(f"**Phone:** {estimate.get('customer_phone', '')}")

    with meta_col2:
        st.write(f"**Address:** {estimate.get('address', '')}")
        st.write(f"**Fence type:** {estimate.get('fence_type', '')}")
        st.write(f"**Yard location:** {estimate.get('yard_location', '')}")

    with meta_col3:
        st.write(f"**Height:** {estimate.get('height_ft', '')} ft")
        st.write(f"**Linear feet:** {estimate.get('linear_feet', '')}")
        st.write(f"**Created:** {estimate.get('created_at', '')}")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        total = estimate.get("estimated_total")
        st.metric("Estimated Total", f"${total:,.2f}" if total is not None else "N/A")

    with metric_col2:
        low = estimate.get("low_range")
        st.metric("Low Range", f"${low:,.2f}" if low is not None else "N/A")

    with metric_col3:
        high = estimate.get("high_range")
        st.metric("High Range", f"${high:,.2f}" if high is not None else "N/A")

    with metric_col4:
        st.metric("Confidence", estimate.get("confidence_score", "N/A"))

    st.write(f"**Status:** {(estimate.get('status') or 'unknown').replace('_', ' ').title()}")

    st.divider()

    st.subheader("Compliance Report")
    render_compliance_report(compliance_report)

    st.subheader("Customer Answers")
    render_customer_answers(missing_answers)

    st.subheader("Line Items")
    render_line_items(estimate_result.get("line_items", []))

    st.subheader("Risk Flags")
    render_risk_flags(estimate_result.get("risk_flags", []))

    st.subheader("Remaining Missing Questions")

    remaining_questions = estimate_result.get("missing_questions", [])
    if remaining_questions:
        for question in remaining_questions:
            st.write(f"- {question}")
    else:
        st.success("No remaining missing questions.")

    st.subheader("Internal Estimator Notes")
    st.text_area(
        "Internal notes",
        value=estimate.get("internal_notes") or estimate_result.get("internal_notes", ""),
        height=300,
        key=f"{key_prefix}_internal_notes_{estimate.get('id')}",
    )

    st.subheader("Customer Proposal Draft")
    st.text_area(
        "Proposal draft",
        value=estimate.get("customer_proposal") or estimate_result.get("customer_proposal", ""),
        height=350,
        key=f"{key_prefix}_proposal_{estimate.get('id')}",
    )

    with st.expander("Raw saved estimate record"):
        st.json(estimate)


def render_saved_estimate_history():
    st.subheader("Saved Estimate History")

    estimates = fetch_saved_estimates()

    if not estimates:
        st.info("No saved estimates found yet.")
        return

    summary_rows = []

    for estimate in estimates:
        summary_rows.append(
            {
                "estimate_id": estimate.get("id"),
                "created_at": estimate.get("created_at"),
                "customer_name": estimate.get("customer_name"),
                "address": estimate.get("address"),
                "fence_type": estimate.get("fence_type"),
                "yard_location": estimate.get("yard_location"),
                "linear_feet": estimate.get("linear_feet"),
                "estimated_total": estimate.get("estimated_total"),
                "status": estimate.get("status"),
                "confidence_score": estimate.get("confidence_score"),
            }
        )

    summary_df = pd.DataFrame(summary_rows)

    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    csv = summary_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Estimate History CSV",
        data=csv,
        file_name="fencescope_estimate_history.csv",
        mime="text/csv",
    )

    st.divider()

    estimate_ids = [estimate.get("id") for estimate in estimates]

    selected_estimate_id = st.selectbox(
        "Select estimate ID to review",
        estimate_ids,
        key="saved_estimate_selector",
    )

    selected_estimate = next(
        estimate for estimate in estimates if estimate.get("id") == selected_estimate_id
    )

    render_estimate_detail(selected_estimate, key_prefix="saved")


def render_latest_session_estimate():
    st.subheader("Latest Session Estimate")

    if not st.session_state.get("estimate_result"):
        st.info(
            "No estimate has been generated in this session yet. Generate an estimate from User View or review saved estimates below."
        )
        return

    result = st.session_state.estimate_result
    compliance_report = st.session_state.get("compliance_report")
    saved_customer = st.session_state.get("latest_saved_customer")
    missing_answers = st.session_state.get("missing_answers", {})

    if saved_customer:
        st.success(f"Latest saved customer ID: {saved_customer.get('id')}")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        st.metric("Estimated Total", f"${result['estimated_total']:,.2f}")

    with metric_col2:
        st.metric("Low Range", f"${result['low_range']:,.2f}")

    with metric_col3:
        st.metric("High Range", f"${result['high_range']:,.2f}")

    with metric_col4:
        st.metric("Confidence", result["confidence_score"])

    st.write(f"**Status:** {result['status'].replace('_', ' ').title()}")

    if result.get("estimate_id"):
        st.caption(f"Saved estimate ID: {result['estimate_id']}")

    if compliance_report:
        st.subheader("Compliance Report")
        render_compliance_report(compliance_report)

    st.subheader("Customer Answers")
    render_customer_answers(missing_answers)

    st.subheader("Line Items")
    render_line_items(result.get("line_items", []))

    st.subheader("Risk Flags")
    render_risk_flags(result.get("risk_flags", []))

    st.subheader("Remaining Missing Questions")

    if result.get("missing_questions"):
        for question in result["missing_questions"]:
            st.write(f"- {question}")
    else:
        st.success("No remaining missing questions.")

    st.subheader("Internal Estimator Notes")
    st.text_area(
        "Internal notes",
        value=result.get("internal_notes", ""),
        height=300,
        key="latest_session_internal_notes",
    )

    st.subheader("Customer Proposal Draft")
    st.text_area(
        "Proposal draft",
        value=result.get("customer_proposal", ""),
        height=350,
        key="latest_session_proposal",
    )

    with st.expander("Raw structured estimate output"):
        st.json(result)


def render_customer_history():
    st.subheader("Customer History")

    try:
        customers = get_all_customers()
    except Exception as error:
        st.error("Could not load customer history from Postgres.")
        st.exception(error)
        return

    if not customers:
        st.info("No customers saved yet. Generate an estimate from User View first.")
        return

    df = pd.DataFrame(customers)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Customer History CSV",
        data=csv,
        file_name="fencescope_customer_history.csv",
        mime="text/csv",
    )

    st.divider()

    st.subheader("Selected Customer Record")

    customer_ids = df["id"].tolist()
    selected_customer_id = st.selectbox("Select customer ID", customer_ids)

    selected_customer = df[df["id"] == selected_customer_id].iloc[0].to_dict()

    st.json(selected_customer)


def render_admin_view():
    st.title("FenceScope AI Admin")
    st.caption("Internal estimate operations dashboard for reviewing saved estimate history.")

    render_latest_session_estimate()

    st.divider()

    render_saved_estimate_history()

    st.divider()

    render_customer_history()


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    st.set_page_config(
        page_title="FenceScope AI",
        page_icon="🏡",
        layout="wide",
    )

    init_db()
    initialize_session_state()

    view = st.sidebar.radio("Choose View", ["User View", "Admin View"])

    render_sidebar()

    if view == "User View":
        render_user_view()
    else:
        render_admin_view()


if __name__ == "__main__":
    main()