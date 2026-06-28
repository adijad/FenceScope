# ui/components/address.py

import requests
import streamlit as st
from streamlit_searchbox import st_searchbox

from ui.api_client import (
    fetch_address_predictions,
    fetch_place_details,
)
from ui.state import reset_workflow_state


def autocomplete_address_options(search_term: str):
    """
    Streamlit searchbox callback.

    Converts backend autocomplete predictions into the list of display labels
    expected by streamlit-searchbox, while storing the prediction metadata in
    session state.
    """
    if not search_term or len(search_term.strip()) < 2:
        return []

    try:
        predictions = fetch_address_predictions(search_term)

        st.session_state.address_prediction_map = {
            prediction["description"]: prediction
            for prediction in predictions
            if prediction.get("description") and prediction.get("place_id")
        }

        return list(st.session_state.address_prediction_map.keys())

    except requests.exceptions.RequestException as error:
        st.warning(f"Address autocomplete failed: {error}")
        return []


def load_selected_place(selected_prediction: str):
    """
    Loads selected Google place details into session state.

    This updates:
    - selected_address
    - map_lat
    - map_lng
    """
    prediction = st.session_state.address_prediction_map.get(selected_prediction)

    if not prediction:
        return

    place_id = prediction.get("place_id")

    if not place_id:
        return

    try:
        place = fetch_place_details(place_id)

        if not place:
            return

        st.session_state.selected_address = place["display_name"]
        st.session_state.map_lat = place["lat"]
        st.session_state.map_lng = place["lng"]

    except requests.exceptions.RequestException as error:
        st.error(f"Could not load selected place: {error}")


def render_address_selector(
    label: str = "Search property address",
    placeholder: str = "Start typing property address...",
    key: str = "property_address_autocomplete",
):
    """
    Reusable address selector component.

    Later, both the guided form flow and the description-intake flow can share this.
    """
    selected_prediction = st_searchbox(
        search_function=autocomplete_address_options,
        placeholder=placeholder,
        label=label,
        key=key,
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

    return {
        "selected_address": selected_address,
        "property_lat": property_lat,
        "property_lng": property_lng,
    }