# ui/theme.py

import streamlit as st


def inject_global_styles():
    st.markdown(
        """
        <style>
        :root {
            --fs-bg: #070b12;
            --fs-surface: #111827;
            --fs-surface-soft: #172033;
            --fs-border: rgba(255, 255, 255, 0.10);
            --fs-text: #f8fafc;
            --fs-muted: #cbd5e1;
            --fs-accent: #ff4b4b;
            --fs-accent-soft: rgba(255, 75, 75, 0.16);
            --fs-blue-soft: rgba(56, 189, 248, 0.12);
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(255, 75, 75, 0.18), transparent 32rem),
                radial-gradient(circle at top right, rgba(56, 189, 248, 0.12), transparent 34rem),
                linear-gradient(135deg, #070b12 0%, #0f172a 48%, #111827 100%);
            color: var(--fs-text);
        }

        .block-container {
            padding-top: 3.2rem;
            padding-bottom: 4rem;
            max-width: 1180px;
        }

        h1, h2, h3 {
            letter-spacing: -0.03em;
        }

        .fs-hero {
            padding: 2rem;
            border: 1px solid var(--fs-border);
            border-radius: 24px;
            background:
                linear-gradient(135deg, rgba(255, 75, 75, 0.16), rgba(56, 189, 248, 0.08)),
                rgba(17, 24, 39, 0.78);
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
            margin-top: 0.65rem;
            margin-bottom: 1.8rem;
        }

        .fs-hero-title {
            font-size: 2.5rem;
            line-height: 1.05;
            font-weight: 800;
            margin-bottom: 0.75rem;
        }

        .fs-hero-subtitle {
            font-size: 1.05rem;
            color: var(--fs-muted);
            max-width: 780px;
        }

        .fs-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1.1rem;
        }

        .fs-pill {
            padding: 0.38rem 0.7rem;
            border-radius: 999px;
            border: 1px solid var(--fs-border);
            background: rgba(255, 255, 255, 0.06);
            color: #e2e8f0;
            font-size: 0.82rem;
        }

        .fs-stepper {
            display: flex;
            gap: 0.7rem;
            flex-wrap: wrap;
            margin: 1.1rem 0 1.4rem 0;
        }

        .fs-step {
            padding: 0.65rem 0.9rem;
            border-radius: 14px;
            border: 1px solid var(--fs-border);
            background: rgba(255, 255, 255, 0.045);
            color: var(--fs-muted);
            font-size: 0.88rem;
        }

        .fs-step-active {
            background: var(--fs-accent-soft);
            border-color: rgba(255, 75, 75, 0.55);
            color: #ffffff;
            font-weight: 700;
        }

        .fs-card {
            border: 1px solid var(--fs-border);
            border-radius: 20px;
            padding: 1.25rem;
            background: rgba(17, 24, 39, 0.78);
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
            min-height: 215px;
            margin-bottom: 0.75rem;
        }

        .fs-card:hover {
            border-color: rgba(255, 75, 75, 0.45);
            transform: translateY(-1px);
            transition: all 160ms ease;
        }

        .fs-card-icon {
            font-size: 1.7rem;
            margin-bottom: 0.7rem;
        }

        .fs-card-title {
            font-size: 1.35rem;
            font-weight: 800;
            margin-bottom: 0.55rem;
        }

        .fs-card-copy {
            color: var(--fs-muted);
            font-size: 0.94rem;
            line-height: 1.55;
        }

        .fs-panel {
            border: 1px solid var(--fs-border);
            border-radius: 22px;
            padding: 1.3rem;
            background: rgba(15, 23, 42, 0.78);
            margin: 1rem 0;
        }

        .fs-section-card {
            border: 1px solid var(--fs-border);
            border-radius: 22px;
            padding: 1.25rem;
            background: rgba(15, 23, 42, 0.82);
            margin: 1rem 0 1.25rem 0;
            box-shadow: 0 14px 36px rgba(0, 0, 0, 0.22);
        }

        .fs-section-title {
            font-size: 1.6rem;
            font-weight: 800;
            margin-bottom: 0.35rem;
        }

        .fs-section-subtitle {
            color: var(--fs-muted);
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }

        .fs-info-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            margin-top: 0.9rem;
        }

        .fs-info-chip {
            padding: 0.42rem 0.75rem;
            border-radius: 999px;
            border: 1px solid var(--fs-border);
            background: rgba(255, 255, 255, 0.05);
            color: #e2e8f0;
            font-size: 0.84rem;
        }

        .fs-highlight-text {
            color: #f8fafc;
            font-weight: 700;
        }

        .stButton > button {
            border-radius: 12px;
            font-weight: 700;
            padding: 0.65rem 1rem;
        }

        .stTextArea textarea,
        .stTextInput input,
        .stNumberInput input {
            border-radius: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero():
    st.markdown(
        """
        <div class="fs-hero">
            <div class="fs-hero-title">FenceScope AI</div>
            <div class="fs-hero-subtitle">
                Turn messy fence quote intake into structured project details, map-based measurements,
                local compliance checks, preliminary pricing, risk triage, and estimator-ready review.
            </div>
            <div class="fs-pill-row">
                <span class="fs-pill">Map measurement</span>
                <span class="fs-pill">Guided intake</span>
                <span class="fs-pill">Text intake</span>
                <span class="fs-pill">Voice intake</span>
                <span class="fs-pill">Compliance pre-check</span>
                <span class="fs-pill">Admin review queue</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stepper(active_step: str):
    steps = [
        ("property", "1. Property"),
        ("intake", "2. Intake"),
        ("review", "3. Review"),
        ("estimate", "4. Estimate"),
        ("admin", "5. Admin Review"),
    ]

    html = '<div class="fs-stepper">'
    for key, label in steps:
        active_class = " fs-step-active" if key == active_step else ""
        html += f'<div class="fs-step{active_class}">{label}</div>'
    html += "</div>"

    st.markdown(html, unsafe_allow_html=True)


def render_workflow_pipeline(title: str = "What happens next?"):
    st.markdown(
        f"""
        <div class="fs-panel">
            <strong>{title}</strong>
            <div class="fs-pill-row">
                <span class="fs-pill">Extract details</span>
                <span class="fs-pill">Ask missing questions</span>
                <span class="fs-pill">Check compliance</span>
                <span class="fs-pill">Calculate pricing</span>
                <span class="fs-pill">Route to admin review</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )