# ui/api_client.py

import requests

from ui.config import (
    API_URL,
    PRECHECK_URL,
    QUESTIONS_URL,
    ESTIMATES_URL,
    ADDRESS_AUTOCOMPLETE_URL,
    ADDRESS_PLACE_URL,
    INTAKE_ANALYZE_TEXT_URL,
    EMAIL_SUMMARY_URL,
    ADMIN_DECISION_URL,
    ADMIN_PROPOSAL_EMAIL_URL,
)


# ---------------------------------------------------------
# Address API calls
# ---------------------------------------------------------

def fetch_address_predictions(query: str) -> list[dict]:
    """
    Calls FastAPI address autocomplete endpoint.
    Returns a list of prediction dicts:
    [
        {"description": "...", "place_id": "..."}
    ]
    """
    response = requests.get(
        ADDRESS_AUTOCOMPLETE_URL,
        params={"q": query},
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("predictions", [])


def fetch_place_details(place_id: str) -> dict | None:
    """
    Calls FastAPI place details endpoint.
    Returns:
    {
        "display_name": "...",
        "lat": ...,
        "lng": ...,
        "place_id": "...",
        "type": "google_place_new"
    }
    """
    response = requests.get(
        ADDRESS_PLACE_URL,
        params={"place_id": place_id},
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("place")


# ---------------------------------------------------------
# Estimate workflow API calls
# ---------------------------------------------------------

def run_precheck(payload: dict) -> dict:
    """
    Runs compliance pre-check before pricing.
    """
    response = requests.post(
        PRECHECK_URL,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def run_missing_questions(payload: dict) -> dict:
    """
    Runs missing-info and risk-question analysis.
    """
    response = requests.post(
        QUESTIONS_URL,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def generate_estimate(payload: dict) -> dict:
    """
    Runs full estimate creation and database save.
    """
    response = requests.post(
        API_URL,
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------
# Unstructured intake API calls
# ---------------------------------------------------------

def analyze_text_intake_request(payload: dict) -> dict:
    """
    Sends customer-written project description to the backend LLM intake agent.

    This endpoint does not create an estimate.
    It only classifies, extracts fields, finds missing info, and returns a structured draft.
    """
    response = requests.post(
        INTAKE_ANALYZE_TEXT_URL,
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------
# Customer email API calls
# ---------------------------------------------------------

def send_customer_summary_email_request(email_payload: dict) -> dict:
    """
    Sends customer-safe preliminary estimate summary.
    """
    response = requests.post(
        EMAIL_SUMMARY_URL,
        json=email_payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------
# Admin API calls
# ---------------------------------------------------------

def fetch_estimates_request(admin_auth) -> list[dict]:
    """
    Loads saved estimates for the admin review queue.
    """
    response = requests.get(
        ESTIMATES_URL,
        auth=admin_auth,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def save_admin_decision_request(
    estimate_id: int,
    payload: dict,
    admin_auth,
) -> dict:
    """
    Saves estimator review status, notes, and email draft.
    """
    response = requests.patch(
        ADMIN_DECISION_URL.format(estimate_id=estimate_id),
        json=payload,
        auth=admin_auth,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_admin_proposal_email_request(
    payload: dict,
    admin_auth,
) -> dict:
    """
    Sends the admin-approved customer email.
    """
    response = requests.post(
        ADMIN_PROPOSAL_EMAIL_URL,
        json=payload,
        auth=admin_auth,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()