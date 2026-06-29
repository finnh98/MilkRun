import json

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from supabase import create_client

from config import API_KEY_FILE, SUPABASE_FILE


def halt(message):
    """Show a Streamlit error and stop the current run."""
    st.error(message)
    st.stop()
    raise RuntimeError(message)


def load_api_key():
    """Load the Google API key from Streamlit secrets, falling back to local JSON."""
    try:
        api_key = st.secrets.get("maps_api_key")
    except StreamlitSecretNotFoundError:
        api_key = None

    if not api_key and API_KEY_FILE.exists():
        try:
            with open(API_KEY_FILE, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            halt(f"{API_KEY_FILE} is not valid JSON: {e}")

        api_key = config.get("maps_api_key")

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        halt(
            "Add your Google Maps API key to Streamlit secrets as "
            "maps_api_key, or put it in maps_api_key.json locally."
        )

    return api_key


def load_supabase_config():
    """Load Supabase URL/key from Streamlit secrets, falling back to local JSON."""
    try:
        supabase_url = st.secrets.get("supabase_url") or st.secrets.get("project_url")
        supabase_key = st.secrets.get("supabase_key")
    except StreamlitSecretNotFoundError:
        supabase_url = None
        supabase_key = None

    if (not supabase_url or not supabase_key) and SUPABASE_FILE.exists():
        try:
            with open(SUPABASE_FILE, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            halt(f"{SUPABASE_FILE} is not valid JSON: {e}")

        supabase_url = supabase_url or config.get("supabase_url") or config.get("project_url")
        supabase_key = supabase_key or config.get("supabase_key")

    if not supabase_url or not supabase_key:
        halt(
            "Add Supabase credentials to Streamlit secrets as supabase_url and "
            "supabase_key, or put them in supabase_detail.json locally."
        )

    return supabase_url, supabase_key


@st.cache_resource
def get_supabase_client():
    """Create and cache the Supabase client for the Streamlit session."""
    supabase_url, supabase_key = load_supabase_config()
    return create_client(supabase_url, supabase_key)


def supabase_error(message, error):
    """Normalize Supabase errors into visible Streamlit errors."""
    halt(f"{message}: {error}")
