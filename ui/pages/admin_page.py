# ui/pages/admin_page.py

import pandas as pd
import requests
import streamlit as st

from ui.api_client import (
    fetch_estimates_request,
    save_admin_decision_request,
    send_admin_proposal_email_request,
)
from ui.auth import get_admin_auth
from ui.components.compliance import render_compliance_snapshot
from ui.components.estimate_summary import (
    render_customer_answers,
    render_line_items,
)
from ui.components.yard_sections import render_yard_sections_table
from ui.formatting import (
    compact_address,
    ensure_dict,
    ensure_list,
    fence_type_label,
    format_currency,
    status_label,
    yard_location_label,
)


REVIEW_STATUS_OPTIONS = {
    "under_review": "Under Review",
    "approved_to_send": "Approved to Send",
    "needs_customer_info": "Needs Customer Info",
    "needs_site_visit": "Needs Site Visit",
    "cannot_quote_as_entered": "Cannot Quote As Entered",
}


def _error_response_text(error: Exception) -> str:
    response = getattr(error, "response", None)

    if response is not None:
        try:
            return response.text
        except Exception:
            return ""

    return ""


def fetch_saved_estimates():
    admin_auth = get_admin_auth()

    if not admin_auth:
        st.warning("Please log in as an admin to view saved estimates.")
        return []

    try:
        return fetch_estimates_request(admin_auth)
    except requests.exceptions.RequestException as error:
        st.error(f"Could not load saved estimates from backend: {error}")

        error_text = _error_response_text(error)
        if error_text:
            st.code(error_text)

        return []


def normalize_review_status(status):
    if not status:
        return "under_review"

    if status == "pending_review":
        return "under_review"

    if status not in REVIEW_STATUS_OPTIONS:
        return "under_review"

    return status


def review_status_label(status):
    status = normalize_review_status(status)
    return REVIEW_STATUS_OPTIONS.get(status, status_label(status))


def review_status_display(estimate):
    review_status = normalize_review_status(estimate.get("admin_decision"))
    email_sent = bool(estimate.get("admin_email_sent"))

    if email_sent:
        sent_labels = {
            "approved_to_send": "Proposal Sent",
            "needs_customer_info": "Info Request Sent",
            "needs_site_visit": "Site Visit Request Sent",
            "cannot_quote_as_entered": "Follow-Up Sent",
            "under_review": "Email Sent",
        }
        return sent_labels.get(review_status, review_status_label(review_status))

    return review_status_label(review_status)


def build_admin_decision_email(estimate, decision, notes):
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
    review_status = normalize_review_status(review_status)

    payload = {
        "admin_decision": review_status,
        "admin_decision_notes": admin_notes,
        "admin_email_subject": email_subject,
        "admin_email_body": email_body,
    }

    try:
        save_admin_decision_request(
            estimate_id=estimate_id,
            payload=payload,
            admin_auth=get_admin_auth(),
        )
        st.success("Review status saved.")
        st.rerun()
    except requests.exceptions.RequestException as error:
        st.error(f"Could not save review status: {error}")

        error_text = _error_response_text(error)
        if error_text:
            st.code(error_text)


def save_then_send_admin_email(
    estimate_id,
    review_status,
    admin_notes,
    to_email,
    subject,
    body,
):
    review_status = normalize_review_status(review_status)

    save_payload = {
        "admin_decision": review_status,
        "admin_decision_notes": admin_notes,
        "admin_email_subject": subject,
        "admin_email_body": body,
    }

    send_payload = {
        "estimate_id": estimate_id,
        "to_email": to_email,
        "subject": subject,
        "body": body,
    }

    try:
        save_admin_decision_request(
            estimate_id=estimate_id,
            payload=save_payload,
            admin_auth=get_admin_auth(),
        )

        send_admin_proposal_email_request(
            payload=send_payload,
            admin_auth=get_admin_auth(),
        )

        st.success(f"Review status saved and email sent to {to_email}.")
        st.rerun()

    except requests.exceptions.RequestException as error:
        st.error(f"Could not save review status or send email: {error}")

        error_text = _error_response_text(error)
        if error_text:
            st.code(error_text)


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
            st.write("**Customer email:** Sent")

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

    review_status_keys = list(REVIEW_STATUS_OPTIONS.keys())

    review_status = st.selectbox(
        "Estimator next step",
        options=review_status_keys,
        index=review_status_keys.index(current_review_status),
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
            or normalize_review_status(review_status) == "under_review"
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
        if normalize_review_status(estimate.get("admin_decision")) == "under_review"
    )

    needs_site_visit = sum(
        1
        for estimate in estimates
        if normalize_review_status(estimate.get("admin_decision")) == "needs_site_visit"
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