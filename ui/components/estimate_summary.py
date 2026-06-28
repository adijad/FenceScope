# ui/components/estimate_summary.py

import pandas as pd
import streamlit as st

from ui.components.yard_sections import render_yard_sections_table
from ui.formatting import (
    ensure_dict,
    format_currency,
    fence_type_label,
    status_label,
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


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


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

    measured_length = _safe_float(
        payload.get("linear_feet", result.get("total_feet", 0)),
        default=0.0,
    )

    with snap_col1:
        st.write(f"**Fence type:** {fence_type_label(payload.get('fence_type'))}")
        st.write(f"**Material grade:** {status_label(payload.get('material_grade'))}")
        st.write(f"**Measured length:** {measured_length:,.1f} ft")
        st.write(f"**Default height:** {payload.get('height_ft', 'N/A')} ft")

    with snap_col2:
        st.write(f"**Walk gates:** {payload.get('gate_count', 0)}")
        st.write(f"**Double gates:** {payload.get('double_gate_count', 0)}")
        st.write(f"**Gate hardware:** {status_label(payload.get('gate_hardware'))}")
        st.write(f"**Old fence removal:** {'Yes' if payload.get('old_fence_removal') else 'No'}")

    with snap_col3:
        st.write(f"**Removal length:** {_safe_float(payload.get('removal_length_feet')):,.1f} ft")
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