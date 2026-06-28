# ui/formatting.py

import json


def format_currency(value):
    if value is None:
        return "N/A"

    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "N/A"


def fence_type_label(fence_type):
    if not fence_type:
        return "N/A"

    return str(fence_type).replace("_", " ").title()


def yard_location_label(location):
    labels = {
        "back": "Back yard",
        "side": "Side yard",
        "front": "Front yard",
    }

    return labels.get(location, str(location).title())


def status_label(status):
    if not status:
        return "Unknown"

    return str(status).replace("_", " ").title()


def ensure_dict(value):
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}

    return {}


def ensure_list(value):
    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return []

    return []


def compact_address(address, max_chars=75):
    if not address:
        return "No address"

    address = str(address)

    if len(address) <= max_chars:
        return address

    return address[: max_chars - 3] + "..."