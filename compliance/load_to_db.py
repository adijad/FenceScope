"""
load_to_db.py
-------------
Reads rules/*.json (from build_rules.py) and upserts each city into Postgres.

Run from compliance/ after `docker compose up -d` and after build_rules.py:
    python load_to_db.py

Idempotent: re-running updates existing cities (upsert on jurisdiction_id).
"""

import json
from pathlib import Path

from compliance.db import get_conn, init_db, list_jurisdictions

# load_to_db.py
RULES_DIR = Path(__file__).parent / "rules"

UPSERT = """
INSERT INTO fence_rules (jurisdiction_id, jurisdiction, source_url, rules, flags, loaded_at)
VALUES (%(jurisdiction_id)s, %(jurisdiction)s, %(source_url)s, %(rules)s, %(flags)s, now())
ON CONFLICT (jurisdiction_id) DO UPDATE SET
    jurisdiction = EXCLUDED.jurisdiction,
    source_url   = EXCLUDED.source_url,
    rules        = EXCLUDED.rules,
    flags        = EXCLUDED.flags,
    loaded_at    = now();
"""


def load_file(conn, path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    conn.execute(UPSERT, {
        "jurisdiction_id": data["jurisdiction_id"],
        "jurisdiction": data["jurisdiction"],
        "source_url": data.get("source_url", ""),
        "rules": json.dumps(data.get("rules", [])),     # psycopg adapts str -> jsonb
        "flags": json.dumps(data.get("flags", [])),
    })
    n = data.get("rule_count", len(data.get("rules", [])))
    f = len(data.get("flags", []))
    print(f"  loaded {data['jurisdiction_id']:<20} {n} rules" + (f", {f} flags" if f else ""))


def main():
    init_db()
    files = sorted(RULES_DIR.glob("*.json"))
    if not files:
        print("No rules/*.json found. Run build_rules.py first.")
        return
    with get_conn() as conn:
        for path in files:
            try:
                load_file(conn, path)
            except Exception as e:
                print(f"  ERROR {path.name}: {e}")
    print("\nDB now contains:", list_jurisdictions())


if __name__ == "__main__":
    main()