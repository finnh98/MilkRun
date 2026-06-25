import base64
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st
import requests


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "farmers.db"
API_KEY_FILE = BASE_DIR / "maps_api_key.json"
LOGO_FILE = BASE_DIR / "milkrun_logo.png"

DEPOT = {
    "name": "Treaty County Trucking",
    "lat": 52.6555680292862,
    "lng": -8.451248793153795,
}

DESTINATION = {
    "name": "Kerry Processing Plant, Charleville",
    "lat": 52.35922556999083,
    "lng": -8.672190576960151,
}


def halt(message):
    st.error(message)
    st.stop()
    raise RuntimeError(message)


def load_api_key():
    api_key = st.secrets.get("maps_api_key")

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


def init_db():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS farmers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    farmer_name TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL
                )
                """
            )
    except sqlite3.Error as e:
        halt(f"Could not initialize {DB_FILE.name}: {e}")


def load_farmers():
    init_db()

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT farmer_name, lat, lng FROM farmers ORDER BY farmer_name"
            ).fetchall()
    except sqlite3.Error as e:
        halt(f"Could not read {DB_FILE.name}: {e}")

    return [dict(row) for row in rows]


def add_farmer(name, lat, lng):
    init_db()

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT INTO farmers (farmer_name, lat, lng) VALUES (?, ?, ?)",
                (name, lat, lng),
            )
    except sqlite3.Error as e:
        halt(f"Could not add farmer to {DB_FILE.name}: {e}")


def stop_payload(stop):
    return {
        "location": {
            "latLng": {
                "latitude": float(stop["lat"]),
                "longitude": float(stop["lng"]),
            }
        }
    }


def maps_location(stop):
    return f"{stop['lat']},{stop['lng']}"


def google_maps_route_url(origin, stops, destination):
    params = {
        "api": "1",
        "origin": maps_location(origin),
        "destination": maps_location(destination),
        "travelmode": "driving",
    }

    if stops:
        params["waypoints"] = "|".join(maps_location(stop) for stop in stops)

    return "https://www.google.com/maps/dir/?" + urlencode(params)


def image_data_uri(path):
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def apply_styles():
    st.set_page_config(
        page_title="MilkRun",
        page_icon=str(LOGO_FILE) if LOGO_FILE.exists() else "M",
        layout="centered",
    )
    st.markdown(
        """
        <style>
            :root {
                --milk-ink: #17211b;
                --milk-muted: #647067;
                --milk-line: #dbe5dc;
                --milk-panel: #f7faf6;
                --milk-accent: #1f7a4d;
                --milk-accent-dark: #16583a;
                --milk-warm: #f0c86a;
            }

            .stApp {
                background:
                    linear-gradient(135deg, rgba(31, 122, 77, 0.10), transparent 34%),
                    linear-gradient(225deg, rgba(240, 200, 106, 0.18), transparent 32%),
                    #fbfdf9;
                color: var(--milk-ink);
            }

            .block-container {
                max-width: 880px;
                padding-top: 2.25rem;
            }

            [data-testid="stSidebar"] {
                background: #eff5ef;
                border-right: 1px solid var(--milk-line);
            }

            h1, h2, h3, label {
                color: var(--milk-ink) !important;
            }

            .milk-header {
                display: flex;
                align-items: center;
                gap: 1rem;
                padding: 1.25rem 1.35rem;
                margin-bottom: 1.25rem;
                border: 1px solid var(--milk-line);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.82);
                box-shadow: 0 18px 45px rgba(23, 33, 27, 0.08);
            }

            .milk-logo {
                width: 58px;
                height: 58px;
                border-radius: 8px;
                object-fit: contain;
                background: white;
                border: 1px solid var(--milk-line);
                box-shadow: 0 8px 22px rgba(23, 33, 27, 0.08);
            }

            .milk-logo-fallback {
                display: grid;
                place-items: center;
                width: 58px;
                height: 58px;
                border-radius: 8px;
                background: var(--milk-accent);
                color: white;
                font-weight: 800;
            }

            .milk-title {
                margin: 0;
                font-size: 2.15rem;
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
                background: rgba(255, 255, 255, 0.86);
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


apply_styles()
render_header()

api_key = load_api_key()

with st.sidebar:
    st.header("MilkRun")
    st.caption("Add farms and build today's route.")

    with st.form("add_farmer"):
        new_name = st.text_input("Farmer name")
        new_lat = st.number_input("Latitude", value=53.3498, format="%.6f")
        new_lng = st.number_input("Longitude", value=-6.2603, format="%.6f")
        submitted = st.form_submit_button("Add farmer")

    if submitted:
        if not new_name.strip():
            st.error("Farmer name is required.")
        else:
            add_farmer(new_name.strip(), new_lat, new_lng)
            st.success(f"Added {new_name.strip()}.")
            st.rerun()

farmers = load_farmers()

if not farmers:
    st.info("Add at least one farmer in the sidebar to create a route.")
    st.stop()
    raise RuntimeError("No farmers found.")

farmer_lookup = {
    farmer["farmer_name"]: {
        "name": farmer["farmer_name"],
        "lat": float(farmer["lat"]),
        "lng": float(farmer["lng"]),
    }
    for farmer in farmers
}

selected_names = st.multiselect(
    "Choose farmers to visit",
    options=list(farmer_lookup.keys()),
    placeholder="Select farmers for the route",
)

if selected_names:
    st.subheader("Selected farmers")
    for i, name in enumerate(selected_names, start=1):
        st.write(f"{i}. {name}")

create_route = st.button("Create optimized route", disabled=not selected_names)

if not create_route:
    st.stop()

origin = DEPOT
destination = DESTINATION
selected_stops = [farmer_lookup[name] for name in selected_names]

body = {
    "origin": stop_payload(origin),
    "destination": stop_payload(destination),
    "intermediates": [stop_payload(stop) for stop in selected_stops],
    "travelMode": "DRIVE",
    "routingPreference": "TRAFFIC_AWARE",
    "computeAlternativeRoutes": False,
    "optimizeWaypointOrder": True,
    "languageCode": "en-US",
    "units": "METRIC",
}

headers = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": api_key,
    "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.optimizedIntermediateWaypointIndex",
}

try:
    response = requests.post(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        json=body,
        headers=headers,
        timeout=30,
    )
except requests.RequestException as e:
    st.error(f"Google Routes request failed: {e}")
    st.stop()

try:
    data = response.json()
except ValueError:
    st.error(f"Google returned a non-JSON response. Status code: {response.status_code}")
    st.text(response.text)
    st.stop()

if response.status_code != 200:
    st.error(f"Google Routes API error. Status code: {response.status_code}")
    st.json(data)
    st.stop()

if "routes" not in data or not data["routes"]:
    st.error("No route returned by Google.")
    st.json(data)
    st.stop()

route = data["routes"][0]
optimized_indexes = route.get("optimizedIntermediateWaypointIndex", [])

if optimized_indexes:
    optimized_stops = [selected_stops[index] for index in optimized_indexes]
else:
    optimized_stops = selected_stops

distance_km = route["distanceMeters"] / 1000
duration = route["duration"]
maps_url = google_maps_route_url(origin, optimized_stops, destination)

st.markdown(
    f"""
    <div class="route-card">
        <div>Start: <strong>{origin['name']}</strong></div>
        <div>End: <strong>{destination['name']}</strong></div>
        <div>Distance: <strong>{distance_km:.2f} km</strong></div>
        <div>Duration: <strong>{duration}</strong></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Optimized stop order")
for i, stop in enumerate(optimized_stops, start=1):
    st.write(f"{i}. {stop['name']}")

st.link_button("Open route in Google Maps", maps_url)
st.code(maps_url, language="text")
