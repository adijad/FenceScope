# ui/layout/sidebar.py

import streamlit as st

from ui.auth import logout_admin


def render_admin_sidebar_status():
    with st.sidebar:
        st.divider()
        st.subheader("Access")

        if st.session_state.get("admin_authenticated"):
            username = st.session_state.get("admin_username") or "admin"
            st.success(f"Admin signed in: {username}")

            if st.button("Log out of Admin"):
                logout_admin()
        else:
            st.caption("Admin Review requires login.")


def render_sidebar():
    with st.sidebar:
        st.header("Workflow")
        st.write(
            """
            1. Capture customer details  
            2. Select property address  
            3. Draw or enter fence measurement  
            4. Break fence into yard sections  
            5. Start guided estimate review  
            6. Run multi-section compliance pre-check  
            7. Answer missing questions  
            8. Generate estimate  
            9. Save estimate for admin review  
            10. Email customer-safe summary
            """
        )

        st.divider()

        st.subheader("System Design")
        st.write(
            """
            **Address autocomplete:** Finds property location  
            **Map:** Measures linear footage  
            **Yard sections:** Captures front, side, and back-yard context  
            **Compliance agent:** Checks local fence code before pricing  
            **Question agent:** Finds missing customer details before estimate  
            **Pricing engine:** Calculates price deterministically  
            **Risk agent:** Routes jobs for estimator review  
            **Proposal agent:** Drafts internal proposal copy  
            **Postgres:** Stores full estimate history  
            **Email action:** Sends customer-approved estimate summary  
            **Human review:** Controls final quote
            """
        )

        st.divider()

        st.caption(
            "Prototype role switcher. In production, this would use authentication, permissions, and audit logs."
        )