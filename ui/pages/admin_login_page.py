# ui/pages/admin_login_page.py

import streamlit as st

from ui.auth import verify_admin_credentials


def render_admin_login():
    st.title("FenceScope AI Admin Login")
    st.caption("Estimator-only access for reviewing submitted fence estimates.")

    st.info("Admin review is protected.")

    with st.container(border=True):
        username = st.text_input("Admin username", key="admin_login_username")
        password = st.text_input(
            "Admin password",
            type="password",
            key="admin_login_password",
        )

        login_clicked = st.button("Log In", type="primary")

        st.caption("To return to the customer intake workflow, choose User View in the sidebar.")

        if login_clicked:
            ok, message = verify_admin_credentials(username, password)

            if ok:
                st.session_state.admin_authenticated = True
                st.session_state.admin_username = username
                st.session_state.admin_password = password
                st.success(message)
                st.rerun()
            else:
                st.error(message)