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
ADMIN_DECISION_URL = "http://127.0.0.1:8000/estimates/{estimate_id}/admin-decision"
ADMIN_PROPOSAL_EMAIL_URL = "http://127.0.0.1:8000/email/admin-approved-proposal"


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


def extract_map_features(map_data):
    """
    Extract both fence measurements and gate marker locations from Leaflet Draw.

    Important behavior:
    - LineString and Polygon drawings are treated as fence geometry.
    - Point drawings are treated as optional gate markers.
    - The latest fence geometry is used for measurement, so adding a marker after
      drawing the fence does not erase the measured footage.
    """
    features = {
        "fence_feet": None,
        "gate_points": [],
    }

    if not map_data:
        return features

    drawings = map_data.get("all_drawings") or []

    if not drawings:
        return features

    fence_measurements = []

    for drawing in drawings:
        geometry = drawing.get("geometry", {})
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")

        if not geometry_type or not coordinates:
            continue

        if geometry_type == "LineString":
            fence_measurements.append(calculate_path_feet(coordinates))

        elif geometry_type == "Polygon":
            outer_ring = coordinates[0] if coordinates else []
            fence_measurements.append(calculate_path_feet(outer_ring))

        elif geometry_type == "Point":
            # GeoJSON Point coordinates are [longitude, latitude].
            lon, lat = coordinates
            features["gate_points"].append(
                {
                    "lat": lat,
                    "lng": lon,
                }
            )

    if fence_measurements:
        features["fence_feet"] = fence_measurements[-1]

    return features


def extract_drawn_measurement_feet(map_data):
    """
    Backward-compatible helper for any old call sites.
    Prefer extract_map_features() when using gate markers.
    """
    return extract_map_features(map_data)["fence_feet"]


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

    st.session_state.email_sent = False
    st.session_state.email_result = None


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
# Display helpers
# ---------------------------------------------------------

def format_currency(value):
    if value is None:
        return "N/A"

    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "N/A"


def fence_type_label(fence_type):
    if not fence_type:
        return "N/A"

    return str(fence_type).replace("_", " ").title()


def yard_location_label(location):
    labels = {
        "back": "Back yard",
        "side": "Side yard",
        "front": "Front yard",
    }

    return labels.get(location, str(location).title())


def status_label(status):
    if not status:
        return "Unknown"

    return str(status).replace("_", " ").title()


def ensure_dict(value):
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}

    return {}


def ensure_list(value):
    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return []

    return []


ADMIN_DECISION_OPTIONS = {
    "under_review": "Under Review",
    "approved_to_send": "Approved to Send",
    "needs_customer_info": "Needs Customer Info",
    "needs_site_visit": "Needs Site Visit",
    "cannot_quote_as_entered": "Cannot Quote As Entered",
}


def admin_decision_label(decision):
    decision = decision or "under_review"
    return ADMIN_DECISION_OPTIONS.get(decision, status_label(decision))


def compact_address(address, max_chars=75):
    if not address:
        return "No address"

    address = str(address)

    if len(address) <= max_chars:
        return address

    return address[: max_chars - 3] + "..."


def review_status_display(estimate):
    review_status = estimate.get("admin_decision") or "under_review"
    email_sent = estimate.get("admin_email_sent")

    if review_status == "pending_review":
        review_status = "under_review"

    if email_sent:
        sent_labels = {
            "approved_to_send": "Proposal Sent",
            "needs_customer_info": "Info Request Sent",
            "needs_site_visit": "Site Visit Request Sent",
            "cannot_quote_as_entered": "Follow-Up Sent",
            "under_review": "Email Sent",
        }
        return sent_labels.get(review_status, status_label(review_status))

    return REVIEW_STATUS_OPTIONS.get(review_status, status_label(review_status))


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
            4. Break fence into yard sections  
            5. Start guided estimate review  
            6. Run multi-section compliance pre-check  
            7. Answer missing questions  
            8. Generate estimate  
            9. Save estimate for admin review  
            10. Email customer-safe summary
            """
        )

        st.divider()

        st.subheader("System Design")
        st.write(
            """
            **Address autocomplete:** Finds property location  
            **Map:** Measures linear footage  
            **Yard sections:** Captures front, side, and back-yard context  
            **Compliance agent:** Checks local fence code before pricing  
            **Question agent:** Finds missing customer details before estimate  
            **Pricing engine:** Calculates price deterministically  
            **Risk agent:** Routes jobs for estimator review  
            **Proposal agent:** Drafts internal proposal copy  
            **Postgres:** Stores full estimate history  
            **Email action:** Sends customer-approved estimate summary  
            **Human review:** Controls final quote
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

    report = ensure_dict(report)

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

    if report.get("review_reasons"):
        with st.expander("Review reasons"):
            for reason in report["review_reasons"]:
                st.write(f"- {reason}")

    if report.get("disclaimer"):
        st.caption(report["disclaimer"])


def render_failed_compliance_guidance(report):
    report = ensure_dict(report)

    failed_rule_ids = [
        finding.get("rule_id", "")
        for finding in report.get("findings", [])
        if finding.get("status") == "fail"
    ]

    st.error(
        "This request cannot be estimated as entered. Please adjust the highlighted fields before generating an estimate."
    )

    if any("fence-height-front-yard" in rule_id for rule_id in failed_rule_ids):
        st.warning(
            "Field to fix: Front-yard fence height. Front-yard fences often have stricter height limits."
        )

    if any("sight" in rule_id or "visibility" in rule_id for rule_id in failed_rule_ids):
        st.warning(
            "Field to review: Front-yard or street-facing fence placement may affect visibility or sight-triangle rules."
        )

    if not failed_rule_ids:
        st.warning(
            "The compliance checker found a blocking issue. Review fence height, yard sections, material, and property address."
        )


def render_risk_flags(risk_flags):
    risk_flags = risk_flags or []

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

    rename_map = {
        "label": "Item",
        "quantity": "Quantity",
        "unit": "Unit",
        "unit_cost": "Unit Cost",
        "total": "Total",
    }

    line_items_df = line_items_df.rename(columns=rename_map)

    if "Unit Cost" in line_items_df.columns:
        line_items_df["Unit Cost"] = line_items_df["Unit Cost"].apply(format_currency)

    if "Total" in line_items_df.columns:
        line_items_df["Total"] = line_items_df["Total"].apply(format_currency)

    st.dataframe(line_items_df, use_container_width=True, hide_index=True)


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


def render_yard_sections_table(yard_sections):
    yard_sections = ensure_list(yard_sections)

    if not yard_sections:
        st.info("No yard section breakdown was provided.")
        return

    rows = []

    for section in yard_sections:
        if not section.get("included", True):
            continue

        rows.append(
            {
                "Yard Section": yard_location_label(section.get("location")),
                "Height": f"{section.get('height_ft', 'N/A')} ft",
                "Approx. Length": (
                    f"{float(section.get('linear_feet')):,.1f} ft"
                    if section.get("linear_feet") is not None
                    else "N/A"
                ),
            }
        )

    if not rows:
        st.info("No included yard sections found.")
        return

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


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

    if not payload.get("yard_sections"):
        missing.append("At least one yard section")

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
                "FenceScope will check local fence-code rules across the selected yard sections, "
                "collect any missing details, generate the estimate, and save it for admin review."
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


# ---------------------------------------------------------
# Customer estimate summary
# ---------------------------------------------------------

def render_estimate_summary(result, payload=None, compliance_report=None):
    if not result:
        st.info("No estimate result available.")
        return

    payload = payload or {}
    compliance_report = ensure_dict(compliance_report)

    st.subheader("Estimate Summary")

    metric_col1, metric_col2, metric_col3 = st.columns(3)

    with metric_col1:
        st.metric("Preliminary Estimate", format_currency(result.get("estimated_total")))

    with metric_col2:
        st.metric("Low Range", format_currency(result.get("low_range")))

    with metric_col3:
        st.metric("High Range", format_currency(result.get("high_range")))

    status = result.get("status")

    if status == "ready_to_send":
        st.success(f"Project Status: {status_label(status)}")
    elif status in ["needs_customer_info", "needs_estimator_review"]:
        st.warning(f"Project Status: {status_label(status)}")
    else:
        st.error(f"Project Status: {status_label(status)}")

    if result.get("estimate_id"):
        st.caption(f"Saved estimate ID: {result['estimate_id']}")

    st.info(
        "This is a preliminary estimate. A representative will review the project details before a final quote is issued."
    )

    st.divider()

    st.subheader("Project Snapshot")

    snap_col1, snap_col2, snap_col3 = st.columns(3)

    with snap_col1:
        st.write(f"**Fence type:** {fence_type_label(payload.get('fence_type'))}")
        st.write(f"**Material grade:** {status_label(payload.get('material_grade'))}")
        st.write(f"**Measured length:** {float(payload.get('linear_feet', result.get('total_feet', 0))):,.1f} ft")
        st.write(f"**Default height:** {payload.get('height_ft', 'N/A')} ft")

    with snap_col2:
        st.write(f"**Walk gates:** {payload.get('gate_count', 0)}")
        st.write(f"**Double gates:** {payload.get('double_gate_count', 0)}")
        st.write(f"**Gate hardware:** {status_label(payload.get('gate_hardware'))}")
        st.write(f"**Old fence removal:** {'Yes' if payload.get('old_fence_removal') else 'No'}")

    with snap_col3:
        st.write(f"**Removal length:** {float(payload.get('removal_length_feet') or 0):,.1f} ft")
        st.write(f"**Slope severity:** {status_label(payload.get('slope_severity'))}")
        st.write(f"**Access level:** {status_label(payload.get('access_level'))}")
        st.write(f"**Brush clearing:** {status_label(payload.get('brush_clearing'))}")
        st.write(f"**Stain/seal:** {'Yes' if payload.get('stain_seal') else 'No'}")
        st.write(f"**Permit/HOA support:** {'Yes' if payload.get('permit_admin') else 'No'}")

    st.subheader("Yard Sections Checked")
    render_yard_sections_table(payload.get("yard_sections", []))

    if compliance_report:
        verdict = compliance_report.get("overall", "NEEDS_REVIEW")
        jurisdiction = compliance_report.get("jurisdiction") or "local jurisdiction"

        if verdict == "PASS":
            st.success(f"Compliance pre-check: {verdict} - {jurisdiction}")
        elif verdict == "FAIL":
            st.error(f"Compliance pre-check: {verdict} - {jurisdiction}")
        else:
            st.warning(f"Compliance pre-check: {verdict} - {jurisdiction}")

        if compliance_report.get("summary"):
            st.caption(compliance_report["summary"])

    st.divider()

    st.subheader("Price Breakdown")
    render_line_items(result.get("line_items", []))

    st.caption(
        "The estimate uses the measured total fence length for pricing. The yard-section breakdown is used to improve compliance checking."
    )

    st.divider()

    st.subheader("What Happens Next")
    st.write(
        """
        A representative will review the project details, confirm final site conditions, 
        check any remaining installation details, and contact you before this becomes a final quote.
        """
    )

    remaining_questions = result.get("missing_questions", [])

    if remaining_questions:
        st.warning(
            "There are a few remaining details for the estimator to confirm. They are saved internally for review."
        )
    else:
        st.success("No remaining customer details are currently required.")


# ---------------------------------------------------------
# Yard section UI
# ---------------------------------------------------------

def render_yard_sections(default_height_ft, total_linear_feet):
    st.subheader("Yard Section Breakdown")

    st.caption(
        "Add the parts of the fence that pass through each yard area. "
        "Front, side, and back yards can have different local fence-height rules."
    )

    yard_sections = []

    with st.container(border=True):
        section_configs = [
            ("back", "Back yard", True),
            ("side", "Side yard", False),
            ("front", "Front yard", False),
        ]

        for location_key, location_label, default_included in section_configs:
            st.markdown(f"**{location_label} section**")

            included = st.checkbox(
                f"Include {location_label.lower()} section",
                value=default_included,
                key=f"{location_key}_section_included",
            )

            col1, col2 = st.columns(2)

            with col1:
                section_height = st.number_input(
                    f"{location_label} height",
                    min_value=3,
                    max_value=10,
                    value=4 if location_key == "front" else int(default_height_ft),
                    step=1,
                    key=f"{location_key}_section_height",
                    disabled=not included,
                )

            with col2:
                default_length = (
                    float(total_linear_feet)
                    if location_key == "back"
                    else 0.0
                )

                section_length = st.number_input(
                    f"{location_label} approximate length",
                    min_value=0.0,
                    value=default_length,
                    step=1.0,
                    key=f"{location_key}_section_length",
                    disabled=not included,
                )

            if included:
                yard_sections.append(
                    {
                        "location": location_key,
                        "included": True,
                        "height_ft": int(section_height),
                        "linear_feet": float(section_length),
                    }
                )

            st.divider()

    if not yard_sections:
        st.warning("Please include at least one yard section.")

        return [
            {
                "location": "back",
                "included": True,
                "height_ft": int(default_height_ft),
                "linear_feet": float(total_linear_feet),
            }
        ]

    entered_section_feet = sum(
        float(section.get("linear_feet") or 0)
        for section in yard_sections
    )

    if entered_section_feet > 0:
        difference = abs(entered_section_feet - float(total_linear_feet))

        if difference > 10:
            st.info(
                "Section lengths do not exactly match the measured total. "
                "That is okay for this demo. Compliance uses section height and location; "
                "pricing still uses the measured total fence length."
            )

    return yard_sections


def derive_primary_yard_location(yard_sections):
    """
    Backend compatibility helper.

    The customer-facing UI uses yard_sections as the source of truth.
    The backend still accepts yard_location, so we derive it from the first
    included section in a stable order.
    """
    for preferred_location in ["back", "side", "front"]:
        for section in yard_sections:
            if (
                section.get("included", True)
                and section.get("location") == preferred_location
            ):
                return preferred_location

    return "back"


def render_map_gate_plan(gate_points, manual_walk_gates, manual_double_gates):
    """
    Lets the user turn map marker points into structured gate counts.

    In the 24-hour MVP, markers do not need to snap to the fence line. They are
    treated as estimator context and converted into walk-gate/double-gate counts
    for pricing and review.
    """
    gate_plan = []
    walk_gate_count_from_map = 0
    double_gate_count_from_map = 0

    st.subheader("Map-Based Gate Placement")
    st.caption(
        "Optional: use the marker tool on the map to place gate locations. "
        "Each marker can be classified as a walk gate or double gate."
    )

    if not gate_points:
        st.info("No gate markers detected. Manual gate counts will be used.")
        return {
            "gate_plan": gate_plan,
            "final_gate_count": int(manual_walk_gates),
            "final_double_gate_count": int(manual_double_gates),
            "use_map_gates": False,
            "gate_plan_notes": "",
        }

    st.success(f"Detected {len(gate_points)} gate marker(s) from the map.")

    use_map_gates = st.checkbox(
        "Use map gate markers for gate counts",
        value=True,
        help=(
            "When selected, FenceScope uses the gate markers below instead of "
            "the manual gate count fields above."
        ),
    )

    with st.container(border=True):
        for idx, gate in enumerate(gate_points):
            st.markdown(f"**Gate {idx + 1}**")

            gate_col1, gate_col2, gate_col3 = st.columns([1.2, 1, 1.4])

            with gate_col1:
                gate_type = st.selectbox(
                    f"Gate {idx + 1} type",
                    ["walk_gate", "double_gate"],
                    format_func=lambda value: {
                        "walk_gate": "Walk gate",
                        "double_gate": "Double gate",
                    }[value],
                    key=f"map_gate_type_{idx}",
                )

            with gate_col2:
                gate_width = st.number_input(
                    f"Gate {idx + 1} width",
                    min_value=3.0,
                    max_value=16.0,
                    value=4.0 if gate_type == "walk_gate" else 10.0,
                    step=1.0,
                    key=f"map_gate_width_{idx}",
                )

            with gate_col3:
                st.caption(
                    f"Location: {gate['lat']:.6f}, {gate['lng']:.6f}"
                )

            gate_plan.append(
                {
                    "gate_number": idx + 1,
                    "gate_type": gate_type,
                    "width_ft": float(gate_width),
                    "lat": gate["lat"],
                    "lng": gate["lng"],
                }
            )

            if gate_type == "walk_gate":
                walk_gate_count_from_map += 1
            else:
                double_gate_count_from_map += 1

            if idx < len(gate_points) - 1:
                st.divider()

    if use_map_gates:
        final_gate_count = walk_gate_count_from_map
        final_double_gate_count = double_gate_count_from_map
        st.write(
            f"**Gate counts used for estimate:** {final_gate_count} walk gate(s), "
            f"{final_double_gate_count} double gate(s)."
        )
    else:
        final_gate_count = int(manual_walk_gates)
        final_double_gate_count = int(manual_double_gates)
        st.write(
            f"**Gate counts used for estimate:** {final_gate_count} manual walk gate(s), "
            f"{final_double_gate_count} manual double gate(s)."
        )

    gate_plan_notes = ""

    if gate_plan:
        gate_plan_notes = "\n\nMap gate placement:\n" + "\n".join(
            [
                (
                    f"- Gate {gate['gate_number']}: "
                    f"{gate['gate_type'].replace('_', ' ')} "
                    f"({gate['width_ft']:.0f} ft), "
                    f"marker at {gate['lat']:.6f}, {gate['lng']:.6f}"
                )
                for gate in gate_plan
            ]
        )

    return {
        "gate_plan": gate_plan,
        "final_gate_count": final_gate_count,
        "final_double_gate_count": final_double_gate_count,
        "use_map_gates": use_map_gates,
        "gate_plan_notes": gate_plan_notes,
    }


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

        material_grade = st.selectbox(
            "Material grade",
            [
                "economy",
                "standard",
                "premium",
            ],
            index=1,
            help="Adjusts the per-foot material/install rate.",
        )

        height_ft = st.number_input(
            "Default fence height",
            min_value=3,
            max_value=10,
            value=6,
            step=1,
            help="Used as the default height for yard sections below.",
        )

        manual_linear_feet = st.number_input(
            "Manual measured fence length fallback",
            min_value=1.0,
            value=186.0,
            step=1.0,
        )

        stain_seal = st.checkbox(
            "Add stain/seal option",
            value=False,
            help="Adds a per-foot stain or seal add-on.",
        )

        access_level = st.selectbox(
            "Access level",
            [
                "easy",
                "limited",
                "difficult",
            ],
            index=0,
            help="Adds a complexity adjustment for limited crew/material access.",
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

        gate_hardware = st.selectbox(
            "Gate hardware",
            [
                "standard",
                "self_closing",
                "lockable",
            ],
            index=0,
            help="Adds hardware upgrade cost per gate.",
        )

        old_fence_removal = st.checkbox("Old fence removal required", value=True)

        removal_length_feet = 0.0

        if old_fence_removal:
            removal_length_feet = st.number_input(
                "Approx. old fence removal length",
                min_value=0.0,
                value=float(manual_linear_feet),
                step=1.0,
                help="Use 0 if unknown. The pricing engine will fall back to total fence length.",
            )

        slope_severity = st.selectbox(
            "Slope severity",
            [
                "none",
                "slight",
                "moderate",
                "steep",
            ],
            index=2,
            help="Adds a complexity adjustment based on slope.",
        )


        brush_clearing = st.selectbox(
            "Brush / obstruction clearing",
            [
                "none",
                "light",
                "moderate",
                "heavy",
            ],
            index=0,
        )

        permit_admin = st.checkbox(
            "Permit / HOA admin support",
            value=False,
            help="Adds a fixed admin support line item.",
        )

        difficult_access = access_level in ["limited", "difficult"]
        slope_present = slope_severity != "none"

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
                "marker": True,
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

    map_features = extract_map_features(map_data)
    drawn_feet = map_features["fence_feet"]
    gate_points = map_features["gate_points"]

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

    gate_plan_result = render_map_gate_plan(
        gate_points=gate_points,
        manual_walk_gates=gate_count,
        manual_double_gates=double_gate_count,
    )

    final_gate_count = gate_plan_result["final_gate_count"]
    final_double_gate_count = gate_plan_result["final_double_gate_count"]
    gate_plan_notes = gate_plan_result["gate_plan_notes"]

    st.divider()

    yard_sections = render_yard_sections(
        default_height_ft=height_ft,
        total_linear_feet=final_linear_feet,
    )

    yard_location = derive_primary_yard_location(yard_sections)

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
        "yard_sections": yard_sections,
        "gate_count": final_gate_count,
        "double_gate_count": final_double_gate_count,
        "old_fence_removal": old_fence_removal,
        "difficult_access": difficult_access,
        "slope_present": slope_present,
        "material_grade": material_grade,
        "gate_hardware": gate_hardware,
        "removal_length_feet": removal_length_feet if old_fence_removal else 0.0,
        "slope_severity": slope_severity,
        "access_level": access_level,
        "brush_clearing": brush_clearing,
        "stain_seal": stain_seal,
        "permit_admin": permit_admin,
        "customer_notes": customer_notes + gate_plan_notes,
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

REVIEW_STATUS_OPTIONS = {
    # Keep this value for backend compatibility.
    # In the UI, we show it as "Under Review".
    "pending_review": "Under Review",
    "approved_to_send": "Approved to Send",
    "needs_customer_info": "Needs Customer Info",
    "needs_site_visit": "Needs Site Visit",
    "cannot_quote_as_entered": "Cannot Quote As Entered",
}


def fetch_saved_estimates():
    try:
        response = requests.get(ESTIMATES_URL, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as error:
        st.error(f"Could not load saved estimates from backend: {error}")
        return []


def normalize_review_status(status):
    """
    Normalize old/new review status values.

    The backend currently stores this in the admin_decision column.
    For now, pending_review is treated as the user-visible Under Review state.
    """
    if not status:
        return "pending_review"

    if status == "under_review":
        return "pending_review"

    if status not in REVIEW_STATUS_OPTIONS:
        return "pending_review"

    return status


def review_status_label(status):
    status = normalize_review_status(status)
    return REVIEW_STATUS_OPTIONS.get(status, status_label(status))


def review_status_display(estimate):
    """
    Single visible status for the admin queue.

    Before email:
    - pending_review -> Under Review
    - needs_customer_info -> Needs Customer Info
    - needs_site_visit -> Needs Site Visit

    After email:
    - needs_customer_info + sent -> Info Request Sent
    - needs_site_visit + sent -> Site Visit Request Sent
    - approved_to_send + sent -> Proposal Sent
    """
    review_status = normalize_review_status(estimate.get("admin_decision"))
    email_sent = bool(estimate.get("admin_email_sent"))

    if email_sent:
        sent_labels = {
            "approved_to_send": "Proposal Sent",
            "needs_customer_info": "Info Request Sent",
            "needs_site_visit": "Site Visit Request Sent",
            "cannot_quote_as_entered": "Follow-Up Sent",
            "pending_review": "Email Sent",
        }
        return sent_labels.get(review_status, review_status_label(review_status))

    return review_status_label(review_status)


def build_admin_decision_email(estimate, decision, notes):
    """
    Builds a customer-facing draft based on the selected Review Status.

    The AI-generated proposal remains available internally, but this draft
    reflects the estimator's human review decision.
    """
    decision = normalize_review_status(decision)

    estimate_result = ensure_dict(estimate.get("estimate_result"))
    compliance_report = ensure_dict(estimate.get("compliance_report"))

    customer_name = estimate.get("customer_name") or "there"
    address = estimate.get("address") or "your property"
    estimated_total = format_currency(estimate.get("estimated_total"))
    low_range = format_currency(estimate.get("low_range"))
    high_range = format_currency(estimate.get("high_range"))

    compliance_overall = compliance_report.get("overall") or "Needs review"
    compliance_jurisdiction = compliance_report.get("jurisdiction") or "local jurisdiction"

    remaining_questions = estimate_result.get("missing_questions", []) or []

    questions_text = "\n".join([f"- {q}" for q in remaining_questions])
    if not questions_text:
        questions_text = "- No additional customer questions are listed right now."

    notes_text = notes.strip() if notes and notes.strip() else ""

    if decision == "approved_to_send":
        subject = f"Your preliminary fence estimate for {address}"
        body = f"""
Hi {customer_name},

We reviewed your fence project details for {address}, and your preliminary estimate is ready.

Preliminary estimate:
{estimated_total}

Expected range:
{low_range} to {high_range}

Compliance pre-check:
{compliance_overall} - {compliance_jurisdiction}

This is still a preliminary estimate. Final pricing may change after final site conditions, material selections, scheduling, and any local requirements are confirmed.

{notes_text}

Best,
FenceScope Estimating Team
""".strip()

    elif decision == "needs_customer_info":
        subject = "A few details needed for your fence estimate"
        body = f"""
Hi {customer_name},

Thank you for submitting your fence project details for {address}.

Before we can continue finalizing your estimate, we need to confirm a few details:

{questions_text}

{notes_text}

Once we have this information, our estimating team can continue reviewing your quote.

Best,
FenceScope Estimating Team
""".strip()

    elif decision == "needs_site_visit":
        subject = "Site visit recommended for your fence estimate"
        body = f"""
Hi {customer_name},

Thank you for submitting your fence project details for {address}.

Based on the information provided, we recommend a site visit before finalizing your quote. This will help us confirm site conditions such as fence layout, slope, access, existing fence removal, property boundaries, and any local compliance considerations.

Preliminary estimate range:
{low_range} to {high_range}

{notes_text}

Please reply with a few times that would work for a site visit.

Best,
FenceScope Estimating Team
""".strip()

    elif decision == "cannot_quote_as_entered":
        subject = "Follow-up needed for your fence request"
        body = f"""
Hi {customer_name},

Thank you for submitting your fence project details for {address}.

After review, we are not able to provide a quote for the project exactly as entered. One or more project details may need to be changed or confirmed before we can continue.

{notes_text or "Our team can help review the details and discuss possible next steps."}

Best,
FenceScope Estimating Team
""".strip()

    else:
        subject = "Update on your FenceScope estimate"
        body = f"""
Hi {customer_name},

Thank you for submitting your fence project details for {address}.

Your estimate is currently being reviewed by our estimating team. We will follow up once the review is complete.

{notes_text}

Best,
FenceScope Estimating Team
""".strip()

    return subject, body


def save_review_status_to_backend(
    estimate_id,
    review_status,
    admin_notes,
    email_subject,
    email_body,
):
    """
    Saves the single visible review status.

    The backend field is still named admin_decision for now.
    """
    review_status = normalize_review_status(review_status)

    payload = {
        "admin_decision": review_status,
        "admin_decision_notes": admin_notes,
        "admin_email_subject": email_subject,
        "admin_email_body": email_body,
    }

    try:
        response = requests.patch(
            ADMIN_DECISION_URL.format(estimate_id=estimate_id),
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        st.success("Review status saved.")
        st.rerun()
    except requests.exceptions.RequestException as error:
        st.error(f"Could not save review status: {error}")
        if getattr(error, "response", None) is not None:
            st.code(error.response.text)


def save_then_send_admin_email(
    estimate_id,
    review_status,
    admin_notes,
    to_email,
    subject,
    body,
):
    """
    Important workflow rule:

    When the estimator sends an email, first save the selected review status
    and edited draft, then send the customer email.

    This prevents the queue card from staying stuck on the previous status.
    """
    review_status = normalize_review_status(review_status)

    save_payload = {
        "admin_decision": review_status,
        "admin_decision_notes": admin_notes,
        "admin_email_subject": subject,
        "admin_email_body": body,
    }

    try:
        save_response = requests.patch(
            ADMIN_DECISION_URL.format(estimate_id=estimate_id),
            json=save_payload,
            timeout=30,
        )
        save_response.raise_for_status()

        send_payload = {
            "estimate_id": estimate_id,
            "to_email": to_email,
            "subject": subject,
            "body": body,
        }

        send_response = requests.post(
            ADMIN_PROPOSAL_EMAIL_URL,
            json=send_payload,
            timeout=60,
        )
        send_response.raise_for_status()

        st.success(f"Review status saved and email sent to {to_email}.")
        st.rerun()

    except requests.exceptions.RequestException as error:
        st.error(f"Could not save review status or send email: {error}")
        if getattr(error, "response", None) is not None:
            st.code(error.response.text)


def render_admin_action_required(estimate):
    estimate_result = ensure_dict(estimate.get("estimate_result"))
    compliance_report = ensure_dict(estimate.get("compliance_report"))
    risk_flags = estimate_result.get("risk_flags", []) or []
    remaining_questions = estimate_result.get("missing_questions", []) or []

    action_items = []

    if compliance_report.get("overall") == "FAIL":
        action_items.append(
            "Compliance failed. The estimator should not approve this estimate as entered."
        )
    elif compliance_report.get("overall") == "NEEDS_REVIEW":
        action_items.append(
            "Review local compliance findings before sending a customer-facing quote."
        )

    for question in remaining_questions:
        action_items.append(f"Confirm with customer: {question}")

    for risk in risk_flags:
        severity = risk.get("severity")
        if severity in ["high", "medium"]:
            recommended_action = risk.get("recommended_action")
            risk_type = risk.get("risk_type", "risk").replace("_", " ").title()

            if recommended_action:
                action_items.append(f"{risk_type}: {recommended_action}")

    if not action_items:
        st.success(
            "No major action items detected. The estimate may be ready for approval after a quick review."
        )
        return

    for item in action_items[:8]:
        st.write(f"- {item}")

    if len(action_items) > 8:
        st.caption(
            f"Showing 8 of {len(action_items)} action items. See Developer Debug for full details."
        )


def render_compliance_snapshot(report):
    report = ensure_dict(report)

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

    passed = []
    needs_review = []
    failed = []

    for finding in report.get("findings", []):
        finding_status = finding.get("status")
        rule_id = finding.get("rule_id", "rule")

        if finding_status == "pass":
            passed.append(rule_id)
        elif finding_status == "fail":
            failed.append(rule_id)
        else:
            needs_review.append(rule_id)

    if failed:
        st.markdown("**Failed**")
        for rule in failed:
            st.write(f"- {rule}")

    if needs_review:
        st.markdown("**Needs review**")
        for rule in needs_review:
            st.write(f"- {rule}")

    if passed:
        st.markdown("**Passed**")
        for rule in passed:
            st.write(f"- {rule}")

    with st.expander("View ordinance details"):
        render_compliance_report(report)


def render_admin_review_card(estimate):
    estimate_id = estimate.get("id")
    estimate_result = ensure_dict(estimate.get("estimate_result"))
    compliance_report = ensure_dict(estimate.get("compliance_report"))
    missing_answers = ensure_dict(estimate.get("missing_answers"))
    yard_sections = ensure_list(estimate.get("yard_sections"))

    current_review_status = normalize_review_status(estimate.get("admin_decision"))
    visible_status = review_status_display(estimate)

    st.subheader(f"Estimate #{estimate_id}")

    meta_col1, meta_col2, meta_col3 = st.columns([1.2, 1.4, 1.4])

    with meta_col1:
        st.write(f"**Customer:** {estimate.get('customer_name', 'Unknown')}")
        st.write(f"**Email:** {estimate.get('customer_email', '') or 'Missing'}")
        st.write(f"**Phone:** {estimate.get('customer_phone', '') or 'Missing'}")

    with meta_col2:
        st.write(f"**Address:** {estimate.get('address', '')}")
        st.write(f"**Fence type:** {fence_type_label(estimate.get('fence_type', ''))}")
        st.write(
            f"**Primary yard:** {yard_location_label(estimate.get('yard_location', ''))}"
        )

    with meta_col3:
        st.write(f"**Created:** {estimate.get('created_at', '')}")
        st.write(f"**Review status:** {visible_status}")

        if estimate.get("admin_updated_at"):
            st.write(f"**Last reviewed:** {estimate.get('admin_updated_at')}")

        if estimate.get("admin_email_sent"):
            st.write(f"**Customer email:** Sent")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        st.metric("Estimate", format_currency(estimate.get("estimated_total")))

    with metric_col2:
        st.metric("Low", format_currency(estimate.get("low_range")))

    with metric_col3:
        st.metric("High", format_currency(estimate.get("high_range")))

    with metric_col4:
        st.metric("Confidence", estimate.get("confidence_score", "N/A"))

    st.divider()

    st.subheader("Review Status")

    review_status = st.selectbox(
        "Estimator next step",
        options=list(REVIEW_STATUS_OPTIONS.keys()),
        index=list(REVIEW_STATUS_OPTIONS.keys()).index(current_review_status),
        format_func=lambda key: REVIEW_STATUS_OPTIONS[key],
        key=f"review_status_{estimate_id}",
    )

    admin_notes = st.text_area(
        "Review notes",
        value=estimate.get("admin_decision_notes") or "",
        key=f"admin_notes_{estimate_id}",
        height=100,
        placeholder="Example: Site visit recommended because of slope and existing fence removal.",
    )

    compliance_failed = compliance_report.get("overall") == "FAIL"
    can_save_or_send = True

    if compliance_failed and review_status == "approved_to_send":
        st.error(
            "This estimate cannot be approved because compliance failed. Choose another review status."
        )
        can_save_or_send = False

    subject_input_key = f"admin_email_subject_input_{estimate_id}"
    body_input_key = f"admin_email_body_input_{estimate_id}"

    if st.button(
        "Update Email Draft From Review Status",
        key=f"build_email_{estimate_id}",
    ):
        subject, body = build_admin_decision_email(
            estimate=estimate,
            decision=review_status,
            notes=admin_notes,
        )
        st.session_state[subject_input_key] = subject
        st.session_state[body_input_key] = body
        st.success("Email draft updated from review status.")

    default_subject = (
        st.session_state.get(subject_input_key)
        or estimate.get("admin_email_subject")
        or f"Your FenceScope estimate for {estimate.get('address')}"
    )

    default_body = (
        st.session_state.get(body_input_key)
        or estimate.get("admin_email_body")
        or estimate.get("customer_proposal")
        or estimate_result.get("customer_proposal", "")
    )

    st.subheader("Customer Email Draft")

    email_subject = st.text_input(
        "Subject",
        value=default_subject,
        key=subject_input_key,
    )

    email_body = st.text_area(
        "Editable customer email",
        value=default_body,
        height=350,
        key=body_input_key,
    )

    if estimate.get("admin_email_sent"):
        st.success(
            f"Customer email already sent at {estimate.get('admin_email_sent_at') or 'unknown time'}."
        )

    save_col, send_col = st.columns(2)

    with save_col:
        if st.button(
            "Save Review Status",
            key=f"save_review_status_{estimate_id}",
            disabled=not can_save_or_send,
        ):
            save_review_status_to_backend(
                estimate_id=estimate_id,
                review_status=review_status,
                admin_notes=admin_notes,
                email_subject=email_subject,
                email_body=email_body,
            )

    with send_col:
        send_disabled = (
            not can_save_or_send
            or normalize_review_status(review_status) == "pending_review"
            or not estimate.get("customer_email")
            or not str(email_subject).strip()
            or not str(email_body).strip()
        )

        if st.button(
            "Send Customer Email",
            key=f"send_customer_email_{estimate_id}",
            disabled=send_disabled,
        ):
            save_then_send_admin_email(
                estimate_id=estimate_id,
                review_status=review_status,
                admin_notes=admin_notes,
                to_email=estimate.get("customer_email"),
                subject=email_subject,
                body=email_body,
            )

    if send_disabled:
        st.caption(
            "To send, choose a non-Under Review status, make sure the customer email exists, and keep the subject/body filled in."
        )

    st.divider()

    with st.expander("Action Required", expanded=True):
        render_admin_action_required(estimate)

    with st.expander("Yard Sections Checked"):
        render_yard_sections_table(yard_sections)

    with st.expander("Pricing Breakdown"):
        render_line_items(estimate_result.get("line_items", []))

    with st.expander("Compliance Snapshot"):
        render_compliance_snapshot(compliance_report)

    with st.expander("Customer Answers"):
        render_customer_answers(missing_answers)

    with st.expander("Internal Estimator Notes"):
        internal_notes = (
            estimate.get("internal_notes")
            or estimate_result.get("internal_notes", "")
        )

        if internal_notes:
            st.write(internal_notes)
        else:
            st.info("No internal estimator notes available.")

    with st.expander("Internal AI Recommendation / Developer Debug"):
        st.write(
            f"**Internal AI recommendation:** {status_label(estimate.get('status'))}"
        )
        st.caption(
            "This is kept for audit/debugging. The queue uses Review Status as the source of truth for operations."
        )
        st.json(estimate)


def render_admin_estimate_card(estimate):
    customer_name = estimate.get("customer_name") or "Unknown customer"
    customer_email = estimate.get("customer_email") or "missing email"
    address = compact_address(estimate.get("address"))
    total = format_currency(estimate.get("estimated_total"))
    badge = review_status_display(estimate)

    label = f"{badge} | {customer_name} | {customer_email} | {address} | {total}"

    with st.expander(label, expanded=False):
        render_admin_review_card(estimate)


def render_admin_review_queue():
    estimates = fetch_saved_estimates()

    if not estimates:
        st.info("No saved estimates found yet.")
        return

    total = len(estimates)

    under_review = sum(
        1
        for estimate in estimates
        if normalize_review_status(estimate.get("admin_decision")) == "pending_review"
    )

    needs_site_visit = sum(
        1
        for estimate in estimates
        if normalize_review_status(estimate.get("admin_decision")) == "needs_site_visit"
    )

    approved = sum(
        1
        for estimate in estimates
        if normalize_review_status(estimate.get("admin_decision")) == "approved_to_send"
    )

    emails_sent = sum(
        1
        for estimate in estimates
        if bool(estimate.get("admin_email_sent"))
    )

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Total Estimates", total)
    metric_col2.metric("Under Review", under_review)
    metric_col3.metric("Site Visits", needs_site_visit)
    metric_col4.metric("Emails Sent", emails_sent)

    st.divider()

    filter_options = ["all"] + list(REVIEW_STATUS_OPTIONS.keys())

    selected_filter = st.selectbox(
        "Filter by review status",
        filter_options,
        format_func=lambda key: "All" if key == "all" else REVIEW_STATUS_OPTIONS[key],
    )

    search_text = st.text_input(
        "Search customer, email, or address",
        placeholder="Example: Aditya, gmail, Patrick Henry",
    ).strip().lower()

    filtered_estimates = estimates

    if selected_filter != "all":
        filtered_estimates = [
            estimate
            for estimate in filtered_estimates
            if normalize_review_status(estimate.get("admin_decision")) == selected_filter
        ]

    if search_text:
        filtered_estimates = [
            estimate
            for estimate in filtered_estimates
            if search_text
            in " ".join(
                [
                    str(estimate.get("customer_name") or ""),
                    str(estimate.get("customer_email") or ""),
                    str(estimate.get("address") or ""),
                ]
            ).lower()
        ]

    if not filtered_estimates:
        st.info("No estimates match this filter.")
        return

    st.subheader("Estimate Review Queue")

    for estimate in filtered_estimates:
        render_admin_estimate_card(estimate)

    st.divider()

    with st.expander("Export estimate queue"):
        summary_rows = []

        for estimate in filtered_estimates:
            yard_sections = ensure_list(estimate.get("yard_sections"))
            included_sections = [
                section.get("location")
                for section in yard_sections
                if section.get("included", True)
            ]

            summary_rows.append(
                {
                    "estimate_id": estimate.get("id"),
                    "created_at": estimate.get("created_at"),
                    "customer_name": estimate.get("customer_name"),
                    "customer_email": estimate.get("customer_email"),
                    "address": estimate.get("address"),
                    "fence_type": estimate.get("fence_type"),
                    "sections_checked": (
                        ", ".join(included_sections) if included_sections else ""
                    ),
                    "linear_feet": estimate.get("linear_feet"),
                    "estimated_total": estimate.get("estimated_total"),
                    "review_status": review_status_display(estimate),
                    "internal_ai_status": estimate.get("status"),
                    "confidence_score": estimate.get("confidence_score"),
                    "customer_email_sent": estimate.get("admin_email_sent"),
                    "customer_email_sent_at": estimate.get("admin_email_sent_at"),
                }
            )

        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        csv = summary_df.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download Estimate Queue CSV",
            data=csv,
            file_name="fencescope_estimate_queue.csv",
            mime="text/csv",
        )


def render_admin_view():
    st.title("FenceScope AI Admin")
    st.caption("Estimator review queue for saved fence estimates.")

    st.info(
        "Every submitted estimate starts in review. The queue status reflects the estimator's next action and customer communication state."
    )

    render_admin_review_queue()


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
