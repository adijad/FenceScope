import math

import folium
import pandas as pd
import requests
import streamlit as st

from folium.plugins import Draw
from streamlit_folium import st_folium
from streamlit_searchbox import st_searchbox


API_URL = "http://127.0.0.1:8000/estimate"
ADDRESS_AUTOCOMPLETE_URL = "http://127.0.0.1:8000/address/autocomplete"
ADDRESS_PLACE_URL = "http://127.0.0.1:8000/address/place"


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


st.set_page_config(
    page_title="FenceScope AI",
    page_icon="🏡",
    layout="wide",
)


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


st.title("FenceScope AI")
st.caption(
    "AI-assisted estimate triage and proposal workflow for residential fencing companies."
)


with st.sidebar:
    st.header("Workflow")
    st.write(
        """
        1. Capture customer details  
        2. Start typing and select property address  
        3. Draw proposed fence line on satellite map  
        4. Generate estimate  
        5. Review risks, missing questions, and proposal  
        6. Approve, revise, or schedule a site visit
        """
    )

    st.divider()

    st.subheader("System Design")
    st.write(
        """
        **Address autocomplete:** Finds property location  
        **Map:** Measures linear footage  
        **Pricing engine:** Calculates price deterministically  
        **Risk agent:** Reviews risks and missing info  
        **Proposal agent:** Drafts customer and internal notes  
        **Human review:** Controls final action
        """
    )


# -----------------------------
# Customer Details
# -----------------------------

st.subheader("1. Customer Details")

customer_col1, customer_col2, customer_col3 = st.columns(3)

with customer_col1:
    customer_name = st.text_input("Customer name", "Sarah Miller")

with customer_col2:
    customer_email = st.text_input("Email address", "sarah@example.com")

with customer_col3:
    customer_phone = st.text_input("Phone number", "(540) 555-0198")


st.divider()


# -----------------------------
# Property Details
# -----------------------------

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


# -----------------------------
# Map Measurement
# -----------------------------

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


# -----------------------------
# Estimate Workflow
# -----------------------------

st.subheader("4. Generate Estimate")

if st.button("Generate Estimate", type="primary"):
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
        "gate_count": gate_count,
        "double_gate_count": double_gate_count,
        "old_fence_removal": old_fence_removal,
        "difficult_access": difficult_access,
        "slope_present": slope_present,
        "customer_notes": customer_notes,
    }

    with st.spinner("Running estimate workflow..."):
        try:
            response = requests.post(API_URL, json=payload, timeout=90)
        except requests.exceptions.RequestException as error:
            st.error(f"Could not connect to backend: {error}")
            st.stop()

    if response.status_code != 200:
        st.error("Backend returned an error.")
        st.code(response.text)
        st.stop()

    result = response.json()

    st.success("Estimate generated successfully.")

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
    elif result["status"] == "needs_customer_info":
        st.warning(f"Status: {status}")
    elif result["status"] == "needs_estimator_review":
        st.warning(f"Status: {status}")
    else:
        st.error(f"Status: {status}")

    st.divider()

    left_col, right_col = st.columns([1, 1])

    with left_col:
        st.subheader("Line Items")

        line_items_df = pd.DataFrame(result["line_items"])
        st.dataframe(line_items_df, use_container_width=True)

        st.subheader("Risk Flags")

        if result["risk_flags"]:
            for risk in result["risk_flags"]:
                severity = risk["severity"].upper()
                st.markdown(
                    f"""
                    **{risk['risk_type'].replace('_', ' ').title()}**  
                    Severity: `{severity}`  
                    {risk['explanation']}  
                    Recommended action: {risk['recommended_action']}
                    """
                )
        else:
            st.write("No major risks flagged.")

    with right_col:
        st.subheader("Missing Questions")

        if result["missing_questions"]:
            for question in result["missing_questions"]:
                st.write(f"- {question}")
        else:
            st.write("No missing questions.")

        st.subheader("Internal Estimator Notes")
        st.text_area(
            "Internal notes",
            value=result["internal_notes"],
            height=300,
        )

    st.divider()

    st.subheader("Customer Proposal Draft")

    st.text_area(
        "Proposal",
        value=result["customer_proposal"],
        height=350,
    )

    st.divider()

    st.subheader("Human Review Actions")

    review_col1, review_col2, review_col3 = st.columns(3)

    with review_col1:
        st.button(
            "Approve Draft",
            disabled=result["status"] != "ready_to_send",
        )

    with review_col2:
        st.button("Request Customer Info")

    with review_col3:
        st.button("Schedule Site Visit")

    st.divider()

    with st.expander("Raw structured output"):
        st.json(result)