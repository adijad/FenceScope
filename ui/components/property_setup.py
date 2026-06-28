# ui/components/property_setup.py

import streamlit as st
from streamlit_searchbox import st_searchbox

from ui.components.address import autocomplete_address_options, load_selected_place
from ui.components.map import render_property_map
from ui.state import reset_workflow_state


# ---------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------

def empty_map_context():
    return {
        "drawn_feet": None,
        "gate_points": [],
        "use_map_measurement": False,
        "final_linear_feet": None,
        "fallback_linear_feet": None,
        "map_data": None,
        "map_ready": False,
    }


def get_saved_map_context():
    return st.session_state.get("property_map_context") or empty_map_context()


def address_has_been_selected():
    return bool(st.session_state.get("last_selected_prediction"))


def section_header(title: str, subtitle: str | None = None):
    st.markdown(f"### {title}")

    if subtitle:
        st.caption(subtitle)


def small_info_card(label: str, value: str, caption: str | None = None):
    with st.container(border=True):
        st.caption(label)
        st.markdown(f"**{value}**")

        if caption:
            st.caption(caption)


def format_coordinates(lat, lng) -> str:
    if lat is None or lng is None:
        return "Coordinates missing"

    try:
        return f"{float(lat):.6f}, {float(lng):.6f}"
    except Exception:
        return "Coordinates missing"


# ---------------------------------------------------------
# Customer details
# ---------------------------------------------------------

def render_customer_details():
    with st.container(border=True):
        section_header(
            "👤 1. Customer Details",
            "Capture the basic contact information needed to save the estimate and send customer-safe follow-up messages.",
        )

        customer_col1, customer_col2, customer_col3 = st.columns(3)

        with customer_col1:
            customer_name = st.text_input(
                "Customer name",
                value=st.session_state.get("customer_name", "Sarah Miller"),
                key="customer_name",
                placeholder="Example: Sarah Miller",
            )

        with customer_col2:
            customer_email = st.text_input(
                "Email address",
                value=st.session_state.get("customer_email", "sarah@example.com"),
                key="customer_email",
                placeholder="Example: sarah@example.com",
            )

        with customer_col3:
            customer_phone = st.text_input(
                "Phone number",
                value=st.session_state.get("customer_phone", "(540) 555-0198"),
                key="customer_phone",
                placeholder="Example: (540) 555-0198",
            )

    return {
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
    }


# ---------------------------------------------------------
# Property address
# ---------------------------------------------------------

def render_property_address_searchbox(
    # label: str = "Search property address",
    placeholder: str = "Start typing property address...",
    key: str = "property_address_autocomplete",
):
    """
    Address selector with custom display.

    We do not call render_address_selector() here because that component prints
    selected address details in a plain style. This function reuses the same
    autocomplete and place-loading logic, but controls the UI locally.
    """

    selected_prediction = st_searchbox(
        search_function=autocomplete_address_options,
        placeholder=placeholder,
        label="",
        key=key,
    )

    if selected_prediction and selected_prediction != st.session_state.get("last_selected_prediction"):
        st.session_state.last_selected_prediction = selected_prediction
        load_selected_place(selected_prediction)
        reset_workflow_state()

        st.success("Address selected. Map center updated.")
        st.rerun()

    selected_address = st.session_state.get("selected_address", "")
    property_lat = st.session_state.get("map_lat", 37.2296)
    property_lng = st.session_state.get("map_lng", -80.4139)

    return {
        "selected_address": selected_address,
        "property_lat": property_lat,
        "property_lng": property_lng,
    }


def render_property_details():
    with st.container(border=True):
        section_header(
            "📍 2. Property Address",
            "Search for the customer property and confirm the address before using map measurement, compliance checks, or estimate generation.",
        )

        property_details = render_property_address_searchbox(
            # label="Search property address",
            placeholder="Start typing property address...",
            key="property_address_autocomplete",
        )

        property_details["address_selected"] = address_has_been_selected()

        selected_address = property_details.get("selected_address") or ""
        property_lat = property_details.get("property_lat")
        property_lng = property_details.get("property_lng")

        if property_details["address_selected"] and selected_address:
            st.success("Property selected successfully.")

            address_col, coord_col = st.columns([2, 1])

            with address_col:
                small_info_card(
                    label="",
                    value=selected_address,
                    caption="Used for map positioning and compliance checks.",
                )

            with coord_col:
                small_info_card(
                    label="Map center",
                    value=format_coordinates(property_lat, property_lng),
                    caption="Latitude and longitude.",
                )
        else:
            st.info("Start typing an address above, then select one of the suggested properties.")

    return property_details


# ---------------------------------------------------------
# Property map
# ---------------------------------------------------------

def render_property_map_setup():
    with st.container(border=True):
        section_header(
            "🗺️ 3. Property Map",
            "Confirm the property location and optionally draw the proposed fence line. FenceScope can use map measurements and gate markers during estimate intake.",
        )

        length_col, guidance_col = st.columns([1, 2])

        with length_col:
            fallback_linear_feet = st.number_input(
                "Fallback fence length",
                min_value=1.0,
                value=float(st.session_state.get("property_setup_fallback_linear_feet", 186.0)),
                step=1.0,
                key="property_setup_fallback_linear_feet",
                help=(
                    "This is used only when no map drawing is available, or when you choose "
                    "not to use the map measurement."
                ),
            )

        with guidance_col:
            with st.container(border=True):
                st.markdown("**Map drawing is optional**")
                st.caption(
                    "Draw a line or polygon for the fence route. Use markers to indicate possible gate locations. "
                    "If you skip drawing, FenceScope will use the fallback length."
                )

        st.markdown("")

        map_result = render_property_map(
            manual_linear_feet=fallback_linear_feet,
            section_title="Property Map and Optional Fence Layout",
            section_caption=(
                "Draw the proposed fence line with the line or polygon tool. "
                "Use markers to indicate possible gate locations."
            ),
            map_key="property_setup_map",
            show_manual_center_controls=True,
        )

        map_context = {
            "drawn_feet": map_result.get("drawn_feet"),
            "gate_points": map_result.get("gate_points", []),
            "use_map_measurement": map_result.get("use_map_measurement", False),
            "final_linear_feet": map_result.get("final_linear_feet", fallback_linear_feet),
            "fallback_linear_feet": fallback_linear_feet,
            "map_data": map_result.get("map_data"),
            "map_ready": True,
        }

        st.session_state.property_map_context = map_context

    return map_context


# ---------------------------------------------------------
# Compact summary after intake mode is selected
# ---------------------------------------------------------

def render_property_summary_card(customer_details: dict, property_details: dict):
    map_context = get_saved_map_context()

    with st.container(border=True):
        section_header(
            "✅ Property Setup Summary",
            "This property context will be used by the selected estimate path.",
        )

        selected_address = property_details.get("selected_address") or "Missing"
        property_lat = property_details.get("property_lat")
        property_lng = property_details.get("property_lng")

        drawn_feet = map_context.get("drawn_feet")
        final_linear_feet = map_context.get("final_linear_feet")
        gate_points = map_context.get("gate_points", [])

        if drawn_feet:
            length_label = "Map measurement"
            length_value = f"{float(drawn_feet):,.1f} ft"
        elif final_linear_feet:
            length_label = "Fallback length"
            length_value = f"{float(final_linear_feet):,.1f} ft"
        else:
            length_label = "Fence length"
            length_value = "Not provided"

        summary_col1, summary_col2, summary_col3 = st.columns(3)

        with summary_col1:
            small_info_card(
                label="Customer",
                value=customer_details.get("customer_name") or "Missing",
                caption=customer_details.get("customer_email") or "Email missing",
            )

        with summary_col2:
            small_info_card(
                label="Property",
                value=selected_address,
                caption=format_coordinates(property_lat, property_lng),
            )

        with summary_col3:
            small_info_card(
                label=length_label,
                value=length_value,
                caption=f"Gate markers: {len(gate_points)}",
            )

        if st.button("Edit property or map", key="edit_property_setup"):
            st.session_state.editing_property_setup = True
            st.rerun()

    return map_context


# ---------------------------------------------------------
# Public setup renderer
# ---------------------------------------------------------

def render_customer_property_setup(compact_when_ready: bool = False):
    """
    Shared setup step.

    Behavior:
    - Before address selection: show customer and address fields.
    - After address selection, before choosing path: show full map.
    - After choosing path: collapse property/map into a summary card.
    """

    customer_details = render_customer_details()

    st.markdown("")

    property_details = render_property_details()

    address_selected = property_details.get("address_selected", False)

    if not address_selected:
        return {
            "customer_name": customer_details["customer_name"],
            "customer_email": customer_details["customer_email"],
            "customer_phone": customer_details["customer_phone"],
            "selected_address": property_details["selected_address"],
            "property_lat": property_details["property_lat"],
            "property_lng": property_details["property_lng"],
            "address_selected": False,
            "map_context": empty_map_context(),
        }

    should_collapse = compact_when_ready and not st.session_state.get(
        "editing_property_setup",
        False,
    )

    if should_collapse:
        st.markdown("")

        map_context = render_property_summary_card(
            customer_details=customer_details,
            property_details=property_details,
        )

    else:
        st.markdown("")

        map_context = render_property_map_setup()

        if compact_when_ready:
            done_col, caption_col = st.columns([1, 3])

            with done_col:
                if st.button("Done editing", key="done_editing_property_setup"):
                    st.session_state.editing_property_setup = False
                    st.rerun()

            with caption_col:
                st.caption("Return to the selected estimate path when you are done updating the property or map.")

    return {
        "customer_name": customer_details["customer_name"],
        "customer_email": customer_details["customer_email"],
        "customer_phone": customer_details["customer_phone"],
        "selected_address": property_details["selected_address"],
        "property_lat": property_details["property_lat"],
        "property_lng": property_details["property_lng"],
        "address_selected": True,
        "map_context": map_context,
    }