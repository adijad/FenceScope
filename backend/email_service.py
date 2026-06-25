# backend/email_service.py

import os
import smtplib
from email.message import EmailMessage
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "FenceScope AI")


def email_configured() -> bool:
    return all(
        [
            SMTP_HOST,
            SMTP_PORT,
            SMTP_USERNAME,
            SMTP_PASSWORD,
            SMTP_FROM_EMAIL,
        ]
    )


def build_estimate_summary_email(
    customer_name: str,
    address: str,
    estimate_id: Optional[int],
    estimated_total: float,
    low_range: float,
    high_range: float,
    status: str,
    confidence_score: float,
    compliance_overall: Optional[str],
    compliance_jurisdiction: Optional[str],
    remaining_questions: list[str],
) -> tuple[str, str]:
    subject = f"Your FenceScope preliminary estimate for {address}"

    status_label = status.replace("_", " ").title()

    if remaining_questions:
        remaining_questions_text = "\n".join(
            [f"- {question}" for question in remaining_questions]
        )
    else:
        remaining_questions_text = "- No remaining missing questions."

    body = f"""
Hi {customer_name},

Thank you for submitting your fence project details through FenceScope AI.

Here is your preliminary estimate summary:

Property:
{address}

Preliminary estimate:
${estimated_total:,.2f}

Expected range:
${low_range:,.2f} to ${high_range:,.2f}

Estimate status:
{status_label}

Compliance pre-check:
{compliance_overall or "Needs review"}{f" - {compliance_jurisdiction}" if compliance_jurisdiction else ""}

Remaining details, if any:
{remaining_questions_text}

A representative will review your project details, confirm any remaining information, and contact you before this becomes a final quote.

Please note: this is a preliminary estimate only. Final pricing may change after estimator review, site conditions, compliance requirements, materials, and scheduling are confirmed.

Best,
FenceScope Estimating Assistant
""".strip()

    return subject, body


def send_email(to_email: str, subject: str, body: str) -> dict:
    if not email_configured():
        raise RuntimeError(
            "SMTP is not configured. Please set SMTP_HOST, SMTP_PORT, "
            "SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM_EMAIL."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)

    return {
        "sent": True,
        "to_email": to_email,
        "subject": subject,
    }


def send_estimate_summary_email(
    to_email: str,
    customer_name: str,
    address: str,
    estimate_id: Optional[int],
    estimated_total: float,
    low_range: float,
    high_range: float,
    status: str,
    confidence_score: float,
    compliance_overall: Optional[str],
    compliance_jurisdiction: Optional[str],
    remaining_questions: list[str],
) -> dict:
    subject, body = build_estimate_summary_email(
        customer_name=customer_name,
        address=address,
        estimate_id=estimate_id,
        estimated_total=estimated_total,
        low_range=low_range,
        high_range=high_range,
        status=status,
        confidence_score=confidence_score,
        compliance_overall=compliance_overall,
        compliance_jurisdiction=compliance_jurisdiction,
        remaining_questions=remaining_questions,
    )

    result = send_email(
        to_email=to_email,
        subject=subject,
        body=body,
    )

    result["body_preview"] = body

    return result

def send_admin_approved_proposal_email(
    to_email: str,
    subject: str,
    body: str,
) -> dict:
    """
    Sends the admin-reviewed customer proposal email.

    This is different from the user-facing preliminary summary email.
    The body should come from the editable admin review draft.
    """
    result = send_email(
        to_email=to_email,
        subject=subject,
        body=body,
    )

    result["body_preview"] = body

    return result