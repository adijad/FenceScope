# backend/storage.py

from psycopg2.extras import Json

from backend.database import get_connection


def create_customer(name: str, email: str, phone: str, address: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO customers (name, email, phone, address)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, email, phone, address, created_at;
        """,
        (name, email, phone, address),
    )

    customer = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    return customer


def create_estimate(
    customer_id: int,
    request_data: dict,
    compliance_report: dict,
    estimate_result: dict,
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO estimates (
            customer_id,
            address,
            property_lat,
            property_lng,
            fence_type,
            yard_location,
            height_ft,
            linear_feet,
            gate_count,
            double_gate_count,
            old_fence_removal,
            difficult_access,
            slope_present,
            customer_notes,
            missing_answers,
            compliance_report,
            estimate_result,
            estimated_total,
            low_range,
            high_range,
            confidence_score,
            status,
            customer_proposal,
            internal_notes
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING *;
        """,
        (
            customer_id,
            request_data.get("address"),
            request_data.get("property_lat"),
            request_data.get("property_lng"),
            request_data.get("fence_type"),
            request_data.get("yard_location"),
            request_data.get("height_ft"),
            request_data.get("linear_feet"),
            request_data.get("gate_count"),
            request_data.get("double_gate_count"),
            request_data.get("old_fence_removal"),
            request_data.get("difficult_access"),
            request_data.get("slope_present"),
            request_data.get("customer_notes"),
            Json(request_data.get("missing_answers") or {}),
            Json(compliance_report or {}),
            Json(estimate_result or {}),
            estimate_result.get("estimated_total"),
            estimate_result.get("low_range"),
            estimate_result.get("high_range"),
            estimate_result.get("confidence_score"),
            estimate_result.get("status"),
            estimate_result.get("customer_proposal"),
            estimate_result.get("internal_notes"),
        ),
    )

    estimate = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    return estimate


def get_all_customers():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, name, email, phone, address, created_at
        FROM customers
        ORDER BY created_at DESC;
        """
    )

    customers = cur.fetchall()

    cur.close()
    conn.close()

    return customers


def get_all_estimates():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            e.id,
            e.created_at,
            e.customer_id,
            c.name AS customer_name,
            c.email AS customer_email,
            c.phone AS customer_phone,
            e.address,
            e.fence_type,
            e.yard_location,
            e.height_ft,
            e.linear_feet,
            e.estimated_total,
            e.low_range,
            e.high_range,
            e.confidence_score,
            e.status,
            e.missing_answers,
            e.compliance_report,
            e.estimate_result,
            e.customer_proposal,
            e.internal_notes
        FROM estimates e
        JOIN customers c ON c.id = e.customer_id
        ORDER BY e.created_at DESC;
        """
    )

    estimates = cur.fetchall()

    cur.close()
    conn.close()

    return estimates