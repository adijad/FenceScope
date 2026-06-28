# ui/config.py

import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

API_URL = f"{API_BASE_URL}/estimate"
PRECHECK_URL = f"{API_BASE_URL}/precheck"
QUESTIONS_URL = f"{API_BASE_URL}/questions"
ESTIMATES_URL = f"{API_BASE_URL}/estimates"

ADDRESS_AUTOCOMPLETE_URL = f"{API_BASE_URL}/address/autocomplete"
ADDRESS_PLACE_URL = f"{API_BASE_URL}/address/place"

INTAKE_ANALYZE_TEXT_URL = f"{API_BASE_URL}/intake/analyze-text"
INTAKE_TRANSCRIBE_AUDIO_URL = f"{API_BASE_URL}/intake/transcribe-audio"

EMAIL_SUMMARY_URL = f"{API_BASE_URL}/email/estimate-summary"
ADMIN_DECISION_URL = f"{API_BASE_URL}/estimates/{{estimate_id}}/admin-decision"
ADMIN_PROPOSAL_EMAIL_URL = f"{API_BASE_URL}/email/admin-approved-proposal"