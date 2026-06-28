import streamlit as st

from backend.database import init_db

from ui.auth import initialize_auth_state
from ui.layout.sidebar import (
    render_admin_sidebar_status,
    render_sidebar,
)
from ui.pages.admin_login_page import render_admin_login
from ui.pages.admin_page import render_admin_view
from ui.pages.user_page import render_user_view
from ui.state import initialize_session_state


def main():
    st.set_page_config(
        page_title="FenceScope AI",
        page_icon="🏡",
        layout="wide",
    )

    init_db()
    initialize_session_state()
    initialize_auth_state()

    view = st.sidebar.radio(
        "Choose View",
        ["User View", "Admin View"],
    )

    render_admin_sidebar_status()
    render_sidebar()

    if view == "User View":
        render_user_view()
        return

    if st.session_state.get("admin_authenticated"):
        render_admin_view()
    else:
        render_admin_login()


if __name__ == "__main__":
    main()