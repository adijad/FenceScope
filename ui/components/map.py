# ui/components/map.py

import math

import folium
import streamlit as st

from folium.plugins import Draw
from streamlit_folium import st_folium

from ui.state import reset_workflow_state


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
# Map rendering
# ---------------------------------------------------------

def render_property_map(
    manual_linear_feet: float,
    section_title: str = "Map-Based Fence Measurement",
    section_caption: str | None = None,
    map_key: str = "fence_map",
    show_manual_center_controls: bool = True,
):
    """
    Reusable property map component.

    Returns:
    {
        "map_data": raw st_folium output,
        "drawn_feet": measured fence length from map,
        "gate_points": list of marker points,
        "use_map_measurement": bool,
        "final_linear_feet": feet used for estimate
    }

    This component is intentionally independent of the guided form so we can
    move the map earlier in the user flow later.
    """

    st.subheader(section_title)

    if section_caption:
        st.caption(section_caption)
    else:
        st.caption(
            "Draw the proposed fence line on the satellite map. "
            "The app calculates total linear footage from the drawn path."
        )

    if show_manual_center_controls:
        map_settings_col, map_col = st.columns([1, 3])
    else:
        map_settings_col = None
        map_col = st.container()

    if show_manual_center_controls and map_settings_col is not None:
        with map_settings_col:
            st.write("Map controls")

            manual_map_lat = st.number_input(
                "Latitude",
                value=float(st.session_state.map_lat),
                format="%.6f",
                key=f"{map_key}_manual_lat",
            )

            manual_map_lng = st.number_input(
                "Longitude",
                value=float(st.session_state.map_lng),
                format="%.6f",
                key=f"{map_key}_manual_lng",
            )

            if st.button("Update Map Center Manually", key=f"{map_key}_update_center"):
                st.session_state.map_lat = manual_map_lat
                st.session_state.map_lng = manual_map_lng
                reset_workflow_state()
                st.rerun()

            st.caption(
                "Manual coordinates are a fallback. In production, Google Places "
                "Autocomplete and Place Details would handle this automatically."
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
            key=map_key,
        )

    map_features = extract_map_features(map_data)
    drawn_feet = map_features["fence_feet"]
    gate_points = map_features["gate_points"]

    if drawn_feet and drawn_feet > 0:
        st.success(f"Measured fence length from map: {drawn_feet:,.2f} linear feet")
        use_map_measurement = st.checkbox(
            "Use map measurement for estimate",
            value=True,
            key=f"{map_key}_use_map_measurement",
        )
    else:
        st.info("Draw a polyline or polygon on the map to calculate fence length.")
        use_map_measurement = False

    final_linear_feet = (
        drawn_feet if use_map_measurement and drawn_feet else manual_linear_feet
    )

    st.write(f"**Linear feet used for estimate:** {final_linear_feet:,.2f}")

    return {
        "map_data": map_data,
        "drawn_feet": drawn_feet,
        "gate_points": gate_points,
        "use_map_measurement": use_map_measurement,
        "final_linear_feet": final_linear_feet,
    }