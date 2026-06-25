"""
jurisdiction.py
---------------
Bridges a Google-formatted address (from backend/address_lookup.py) to a
jurisdiction_id that exists in the fence_rules table.

Flow:
    address string -> search_address() -> display_name like
    "888 University City Blvd, Blacksburg, VA 24060, USA"
    -> parse city + state -> match to a loaded jurisdiction_id -> "va_blacksburg"

If the city isn't one we have rules for, returns None so the agent can REFUSE
and escalate instead of guessing.
"""

import re

# city/state -> jurisdiction_id, for the cities currently loaded in Postgres.
# Keep this in sync with what load_to_db.py loaded (or generate it from the DB).
KNOWN_JURISDICTIONS = {
    ("fresno", "ca"): "ca_fresno",
    ("oakland", "ca"): "ca_oakland",
    ("san jose", "ca"): "ca_san_jose",
    ("blacksburg", "va"): "va_blacksburg",
    ("harrisonburg", "va"): "va_harrisonburg",
    ("lynchburg", "va"): "va_lynchburg",
    ("roanoke", "va"): "va_roanoke",
}


def parse_city_state(display_name: str) -> tuple[str | None, str | None]:
    """Pull (city_lower, state_lower) out of a Google formatted address.

    Format is reliably: "<street>, <City>, <ST> <zip>, USA"
    so the state+zip chunk is the field matching '<ST> <zip>', and the city
    is the comma-field immediately before it.
    """
    if not display_name:
        return None, None
    parts = [p.strip() for p in display_name.split(",")]
    state = None
    city = None
    for i, part in enumerate(parts):
        m = re.match(r"^([A-Z]{2})\s+\d{5}", part)        # "VA 24060"
        if m:
            state = m.group(1).lower()
            if i - 1 >= 0:
                city = parts[i - 1].lower()
            break
    return city, state


def resolve_jurisdiction(display_name: str) -> dict:
    """Return {'jurisdiction_id', 'city', 'state', 'matched': bool}."""
    city, state = parse_city_state(display_name)
    jid = KNOWN_JURISDICTIONS.get((city, state)) if city and state else None
    return {
        "jurisdiction_id": jid,
        "city": city,
        "state": state,
        "matched": jid is not None,
    }


if __name__ == "__main__":
    tests = [
        "888 University City Blvd, Blacksburg, VA 24060, USA",
        "1 Fulton St, Fresno, CA 93721, USA",
        "100 Main St, Richmond, VA 23219, USA",   # NOT in our 7 -> should not match
    ]
    for t in tests:
        print(t, "->", resolve_jurisdiction(t))