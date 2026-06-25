"""
db.py
-----
Postgres connection + schema + the single lookup the compliance agent uses.

Reads DATABASE_URL from .env (matches the docker-compose POSTGRES_* values):
    DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db>

Table: fence_rules
  jurisdiction_id  TEXT PK    e.g. 'ca_fresno'
  jurisdiction     TEXT       e.g. 'Fresno, CA'
  source_url       TEXT
  rules            JSONB      the structured rule array
  flags            JSONB      human-review flags from build_rules.py
  loaded_at        TIMESTAMPTZ
"""

import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS fence_rules (
    jurisdiction_id TEXT PRIMARY KEY,
    jurisdiction    TEXT NOT NULL,
    source_url      TEXT,
    rules           JSONB NOT NULL,
    flags           JSONB,
    loaded_at       TIMESTAMPTZ DEFAULT now()
);
"""


def get_conn():
    return psycopg.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        conn.execute(SCHEMA)
    print("schema ready: fence_rules")


def get_rules(jurisdiction_id: str) -> dict | None:
    """The agent's lookup. Returns the full record for a city, or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT jurisdiction, source_url, rules, flags "
            "FROM fence_rules WHERE jurisdiction_id = %s",
            (jurisdiction_id,),
        ).fetchone()
    if not row:
        return None
    return {"jurisdiction": row[0], "source_url": row[1], "rules": row[2], "flags": row[3]}


def list_jurisdictions() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT jurisdiction_id FROM fence_rules ORDER BY jurisdiction_id"
        ).fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    init_db()
    print("jurisdictions in DB:", list_jurisdictions())