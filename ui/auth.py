# ui/auth.py

import hmac
import os

import streamlit as st


def initialize_auth_state():
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    if "admin_username" not in st.session_state:
        st.session_state.admin_username = ""

    if "admin_password" not in st.session_state:
        st.session_state.admin_password = ""


def get_admin_auth():
    """
    Returns an HTTP Basic auth tuple for backend admin endpoints.
    Returns None when the admin is not logged in.
    """

    if not st.session_state.get("admin_authenticated"):
        return None

    username = st.session_state.get("admin_username", "")
    password = st.session_state.get("admin_password", "")

    if not username or not password:
        return None

    return (username, password)


def clear_admin_auth_state():
    st.session_state.admin_authenticated = False
    st.session_state.admin_username = ""
    st.session_state.admin_password = ""


def logout_admin():
    clear_admin_auth_state()
    st.rerun()


def get_secret_value(name: str, default=None):
    """
    Reads from Streamlit secrets in production and falls back to environment variables locally.
    """

    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name, default)


def verify_admin_credentials(username: str, password: str):
    expected_username = get_secret_value("ADMIN_USERNAME")
    expected_password = get_secret_value("ADMIN_PASSWORD")

    if not expected_username or not expected_password:
        return False, "Admin credentials are not configured."

    username_ok = hmac.compare_digest(username or "", expected_username)
    password_ok = hmac.compare_digest(password or "", expected_password)

    if username_ok and password_ok:
        st.session_state.admin_authenticated = True
        return True, "Admin login successful."

    return False, "Invalid admin username or password."