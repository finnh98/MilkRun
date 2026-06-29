import base64

import streamlit as st

from config import LOGO_FILE


def image_data_uri(path):
    """Embed the local logo image directly into the rendered page."""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def apply_styles():
    """Configure the Streamlit page and inject MilkRun's visual theme."""
    st.set_page_config(
        page_title="MilkRun",
        page_icon=str(LOGO_FILE) if LOGO_FILE.exists() else "M",
        layout="centered",
    )
    st.markdown(
        """
        <style>
            :root {
                --milk-ink: #102033;
                --milk-muted: #5d7188;
                --milk-line: #c8d8ea;
                --milk-panel: #f5f9fd;
                --milk-accent: #1769aa;
                --milk-accent-dark: #0a315c;
                --milk-accent-light: #d8ecff;
            }

            .stApp {
                background:
                    linear-gradient(135deg, rgba(10, 49, 92, 0.12), transparent 36%),
                    linear-gradient(225deg, rgba(23, 105, 170, 0.16), transparent 34%),
                    linear-gradient(180deg, #f7fbff 0%, #eef6ff 100%);
                color: var(--milk-ink);
            }

            .block-container {
                max-width: 880px;
                padding-top: 2.25rem;
            }

            [data-testid="stSidebar"] {
                background: #edf6ff;
                border-right: 1px solid var(--milk-line);
            }

            h1, h2, h3, label {
                color: var(--milk-ink) !important;
            }

            .milk-header {
                display: flex;
                align-items: center;
                gap: 1.2rem;
                padding: 1.35rem 1.45rem;
                margin-bottom: 1.25rem;
                border: 1px solid var(--milk-line);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.9);
                box-shadow: 0 18px 48px rgba(10, 49, 92, 0.12);
            }

            .milk-logo {
                width: 82px;
                height: 82px;
                border-radius: 8px;
                object-fit: contain;
                background: white;
                border: 1px solid var(--milk-line);
                box-shadow: 0 10px 28px rgba(10, 49, 92, 0.14);
            }

            .milk-logo-fallback {
                display: grid;
                place-items: center;
                width: 82px;
                height: 82px;
                border-radius: 8px;
                background: var(--milk-accent);
                color: white;
                font-weight: 800;
            }

            .milk-title {
                margin: 0;
                font-size: 2.35rem;
                line-height: 1;
                font-weight: 800;
                letter-spacing: 0;
            }

            .milk-subtitle {
                margin-top: 0.35rem;
                color: var(--milk-muted);
                font-size: 0.98rem;
            }

            .route-card {
                padding: 1rem 1.1rem;
                margin: 1rem 0;
                border: 1px solid var(--milk-line);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.9);
            }

            .route-card.completed {
                opacity: 0.56;
                filter: grayscale(0.65);
                background: rgba(232, 240, 248, 0.78);
            }

            .route-stops.completed {
                opacity: 0.56;
                filter: grayscale(0.65);
            }

            .route-title {
                margin-bottom: 0.45rem;
                color: var(--milk-accent-dark);
                font-size: 1.1rem;
                font-weight: 800;
            }

            .route-card strong {
                color: var(--milk-accent-dark);
            }

            div.stButton > button,
            div.stLinkButton > a {
                border-radius: 8px;
                border: 1px solid var(--milk-accent-dark);
                background: var(--milk-accent);
                color: white;
                font-weight: 700;
            }

            div.stButton > button:hover,
            div.stLinkButton > a:hover {
                border-color: var(--milk-accent-dark);
                background: var(--milk-accent-dark);
                color: white;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    """Render the branded MilkRun header."""
    logo_markup = (
        f'<img class="milk-logo" src="{image_data_uri(LOGO_FILE)}" alt="MilkRun logo">'
        if LOGO_FILE.exists()
        else '<div class="milk-logo-fallback">MR</div>'
    )
    st.markdown(
        f"""
        <div class="milk-header">
            {logo_markup}
            <div>
                <h1 class="milk-title">MilkRun</h1>
                <div class="milk-subtitle">Optimized farm collection routes for the day.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_route_card(route_title, start_name, end_name, distance_km, duration, completed=False):
    """Render the shared route summary card used by manager and driver pages."""
    completed_class = " completed" if completed else ""
    st.markdown(
        f"""
        <div class="route-card{completed_class}">
            <div class="route-title">{route_title}</div>
            <div>Start: <strong>{start_name}</strong></div>
            <div>End: <strong>{end_name}</strong></div>
            <div>Distance: <strong>{distance_km:.2f} km</strong></div>
            <div>Duration: <strong>{duration}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
