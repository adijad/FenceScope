# backend/database.py

import os

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing. Check your .env file.")

    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            address TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS estimates (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,

            address TEXT NOT NULL,
            property_lat DOUBLE PRECISION,
            property_lng DOUBLE PRECISION,

            fence_type TEXT NOT NULL,
            yard_location TEXT NOT NULL,
            yard_sections JSONB,
            height_ft INTEGER NOT NULL,
            linear_feet DOUBLE PRECISION NOT NULL,

            gate_count INTEGER DEFAULT 0,
            double_gate_count INTEGER DEFAULT 0,
            old_fence_removal BOOLEAN DEFAULT FALSE,
            difficult_access BOOLEAN DEFAULT FALSE,
            slope_present BOOLEAN DEFAULT FALSE,

            customer_notes TEXT,
            missing_answers JSONB,
            compliance_report JSONB,
            estimate_result JSONB,

            estimated_total DOUBLE PRECISION,
            low_range DOUBLE PRECISION,
            high_range DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            status TEXT,

            customer_proposal TEXT,
            internal_notes TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        ALTER TABLE estimates
        ADD COLUMN IF NOT EXISTS yard_sections JSONB;
        """
    )
    cur.execute(
        """
        ALTER TABLE estimates
        ADD COLUMN IF NOT EXISTS admin_decision TEXT DEFAULT 'pending_review',
        ADD COLUMN IF NOT EXISTS admin_decision_notes TEXT,
        ADD COLUMN IF NOT EXISTS admin_email_subject TEXT,
        ADD COLUMN IF NOT EXISTS admin_email_body TEXT,
        ADD COLUMN IF NOT EXISTS admin_email_sent BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS admin_email_sent_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS admin_updated_at TIMESTAMP;
        """
    )

    conn.commit()
    cur.close()
    conn.close()