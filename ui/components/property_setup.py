# # ui/components/property_setup.py

# import streamlit as st

# from ui.components.address import render_address_selector
# from ui.components.map import render_property_map


# def render_customer_details():
#     st.subheader("1. Customer Details")

#     customer_col1, customer_col2, customer_col3 = st.columns(3)

#     with customer_col1:
#         customer_name = st.text_input(
#             "Customer name",
#             value="Sarah Miller",
#             key="customer_name",
#         )

#     with customer_col2:
#         customer_email = st.text_input(
#             "Email address",
#             value="sarah@example.com",
#             key="customer_email",
#         )

#     with customer_col3:
#         customer_phone = st.text_input(
#             "Phone number",
#             value="(540) 555-0198",
#             key="customer_phone",
#         )

#     return {
#         "customer_name": customer_name,
#         "customer_email": customer_email,
#         "customer_phone": customer_phone,
#     }


# def address_has_been_selected():
#     """
#     The map should render only after the user actively selects an address
#     from the autocomplete searchbox.
#     """

#     return bool(st.session_state.get("last_selected_prediction"))


# def empty_map_context():
#     return {
#         "drawn_feet": None,
#         "gate_points": [],
#         "use_map_measurement": False,
#         "final_linear_feet": None,
#         "fallback_linear_feet": None,
#         "map_data": None,
#         "map_ready": False,
#     }


# def render_property_details():
#     st.subheader("2. Property Address")

#     property_details = render_address_selector(
#         label="Search property address",
#         placeholder="Start typing property address...",
#         key="property_address_autocomplete",
#     )

#     property_details["address_selected"] = address_has_been_selected()

#     return property_details


# def render_property_map_setup():
#     """
#     Only call this after an address has been selected.
#     """

#     st.subheader("3. Property Map")

#     st.caption(
#         "Confirm the property location and optionally draw the proposed fence line. "
#         "This map context will be shared by both the guided form and the future description-based intake."
#     )

#     fallback_linear_feet = st.number_input(
#         "Approximate fence length if you do not draw on the map",
#         min_value=1.0,
#         value=186.0,
#         step=1.0,
#         key="property_setup_fallback_linear_feet",
#         help=(
#             "This is only used when no map drawing is available, or when you choose not to use the map measurement."
#         ),
#     )

#     map_result = render_property_map(
#         manual_linear_feet=fallback_linear_feet,
#         section_title="Property Map and Optional Fence Layout",
#         section_caption=(
#             "Draw the proposed fence line with the line or polygon tool. "
#             "Use markers to indicate possible gate locations."
#         ),
#         map_key="property_setup_map",
#         show_manual_center_controls=True,
#     )

#     return {
#         "drawn_feet": map_result.get("drawn_feet"),
#         "gate_points": map_result.get("gate_points", []),
#         "use_map_measurement": map_result.get("use_map_measurement", False),
#         "final_linear_feet": map_result.get("final_linear_feet", fallback_linear_feet),
#         "fallback_linear_feet": fallback_linear_feet,
#         "map_data": map_result.get("map_data"),
#         "map_ready": True,
#     }


# def render_customer_property_setup():
#     """
#     Shared setup step for both future intake paths.

#     Flow:
#     - Customer details
#     - Address search
#     - Map section appears only after the user selects an address
#     """

#     customer_details = render_customer_details()

#     st.divider()

#     property_details = render_property_details()

#     address_selected = property_details.get("address_selected", False)

#     if address_selected:
#         st.divider()
#         map_context = render_property_map_setup()
#     else:
#         map_context = empty_map_context()

#     return {
#         "customer_name": customer_details["customer_name"],
#         "customer_email": customer_details["customer_email"],
#         "customer_phone": customer_details["customer_phone"],
#         "selected_address": property_details["selected_address"],
#         "property_lat": property_details["property_lat"],
#         "property_lng": property_details["property_lng"],
#         "address_selected": address_selected,
#         "map_context": map_context,
#     }


# ui/components/property_setup.py

import streamlit as st

from ui.components.address import render_address_selector
from ui.components.map import render_property_map


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


def render_customer_details():
    st.subheader("1. Customer Details")

    customer_col1, customer_col2, customer_col3 = st.columns(3)

    with customer_col1:
        customer_name = st.text_input(
            "Customer name",
            value="Sarah Miller",
            key="customer_name",
        )

    with customer_col2:
        customer_email = st.text_input(
            "Email address",
            value="sarah@example.com",
            key="customer_email",
        )

    with customer_col3:
        customer_phone = st.text_input(
            "Phone number",
            value="(540) 555-0198",
            key="customer_phone",
        )

    return {
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
    }


def address_has_been_selected():
    return bool(st.session_state.get("last_selected_prediction"))


def render_property_details():
    st.subheader("2. Property Address")

    property_details = render_address_selector(
        label="Search property address",
        placeholder="Start typing property address...",
        key="property_address_autocomplete",
    )

    property_details["address_selected"] = address_has_been_selected()

    return property_details


def render_property_map_setup():
    st.subheader("3. Property Map")

    st.caption(
        "Confirm the property location and optionally draw the proposed fence line. "
        "This map context will be shared by both estimate paths."
    )

    fallback_linear_feet = st.number_input(
        "Approximate fence length if you do not draw on the map",
        min_value=1.0,
        value=186.0,
        step=1.0,
        key="property_setup_fallback_linear_feet",
        help=(
            "This is only used when no map drawing is available, or when you choose not to use the map measurement."
        ),
    )

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


def render_property_summary_card(customer_details: dict, property_details: dict):
    map_context = get_saved_map_context()

    with st.container(border=True):
        st.markdown("### Property setup")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.write(f"**Customer:** {customer_details.get('customer_name') or 'Missing'}")
            st.write(f"**Email:** {customer_details.get('customer_email') or 'Missing'}")

        with col2:
            st.write(f"**Address:** {property_details.get('selected_address') or 'Missing'}")
            st.write(
                f"**Coordinates:** {property_details.get('property_lat'):.6f}, {property_details.get('property_lng'):.6f}"
            )

        with col3:
            drawn_feet = map_context.get("drawn_feet")
            final_linear_feet = map_context.get("final_linear_feet")
            gate_points = map_context.get("gate_points", [])

            if drawn_feet:
                st.write(f"**Map measurement:** {float(drawn_feet):,.1f} ft")
            elif final_linear_feet:
                st.write(f"**Fallback length:** {float(final_linear_feet):,.1f} ft")
            else:
                st.write("**Length:** Not provided")

            st.write(f"**Gate markers:** {len(gate_points)}")

        if st.button("Edit property or map", key="edit_property_setup"):
            st.session_state.editing_property_setup = True
            st.rerun()

    return map_context


def render_customer_property_setup(compact_when_ready: bool = False):
    """
    Shared setup step.

    Behavior:
    - Before address selection: show customer and address fields.
    - After address selection, before choosing path: show full map.
    - After choosing path: collapse property/map into a summary card.
    """

    customer_details = render_customer_details()

    st.divider()

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
        st.divider()
        map_context = render_property_summary_card(
            customer_details=customer_details,
            property_details=property_details,
        )
    else:
        st.divider()
        map_context = render_property_map_setup()

        if compact_when_ready:
            if st.button("Done editing property/map", key="done_editing_property_setup"):
                st.session_state.editing_property_setup = False
                st.rerun()

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