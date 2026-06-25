# backend/storage.py

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