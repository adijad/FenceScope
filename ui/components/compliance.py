# ui/components/compliance.py

import streamlit as st

from ui.formatting import ensure_dict


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