# ui/components/yard_sections.py

import pandas as pd
import streamlit as st

from ui.formatting import ensure_list, yard_location_label


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