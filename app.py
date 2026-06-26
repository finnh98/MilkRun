import base64
import json
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st
import requests
from streamlit.errors import StreamlitSecretNotFoundError


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "farmers.db"
DRIVERS_DB_FILE = BASE_DIR / "drivers.db"
ROUTES_DB_FILE = BASE_DIR / "routes.db"
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

DEFAULT_DRIVERS = [
    ("Tom", "+353 85 111 2222"),
    ("Peter", "+353 87 123 4567"),
    ("Paul", "+353 86 234 5678"),
]


def halt(message):
    st.error(message)
    st.stop()
    raise RuntimeError(message)


def load_api_key():
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


def init_drivers_db():
    try:
        with sqlite3.connect(DRIVERS_DB_FILE) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drivers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    phone TEXT NOT NULL
                )
                """
            )
            default_names = [name for name, _ in DEFAULT_DRIVERS]
            conn.execute(
                f"DELETE FROM drivers WHERE name NOT IN ({','.join('?' for _ in default_names)})",
                default_names,
            )
            for name, phone in DEFAULT_DRIVERS:
                conn.execute(
                    """
                    INSERT INTO drivers (name, phone)
                    VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET phone = excluded.phone
                    """,
                    (name, phone),
                )
    except sqlite3.Error as e:
        halt(f"Could not initialize {DRIVERS_DB_FILE.name}: {e}")


def load_drivers():
    init_drivers_db()

    try:
        with sqlite3.connect(DRIVERS_DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT name, phone FROM drivers ORDER BY name"
            ).fetchall()
    except sqlite3.Error as e:
        halt(f"Could not read {DRIVERS_DB_FILE.name}: {e}")

    return [dict(row) for row in rows]


def init_routes_db():
    try:
        with sqlite3.connect(ROUTES_DB_FILE) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assigned_routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_title TEXT,
                    route_date TEXT NOT NULL,
                    driver_name TEXT NOT NULL,
                    driver_phone TEXT NOT NULL,
                    start_name TEXT NOT NULL,
                    end_name TEXT NOT NULL,
                    farmer_names_json TEXT NOT NULL,
                    google_maps_url TEXT NOT NULL,
                    distance_km REAL NOT NULL,
                    duration TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(assigned_routes)").fetchall()
            }
            if "route_title" not in columns:
                conn.execute("ALTER TABLE assigned_routes ADD COLUMN route_title TEXT")
            if "completed" not in columns:
                conn.execute(
                    "ALTER TABLE assigned_routes ADD COLUMN completed INTEGER NOT NULL DEFAULT 0"
                )
            backfill_route_titles(conn)
    except sqlite3.Error as e:
        halt(f"Could not initialize {ROUTES_DB_FILE.name}: {e}")


def backfill_route_titles(conn):
    rows = conn.execute(
        """
        SELECT id, route_date
        FROM assigned_routes
        WHERE route_title IS NULL OR route_title = ''
        ORDER BY route_date, id
        """
    ).fetchall()
    route_counts = {}

    for route_id, route_date in rows:
        if route_date not in route_counts:
            route_counts[route_date] = conn.execute(
                """
                SELECT COUNT(*)
                FROM assigned_routes
                WHERE route_date = ?
                  AND route_title IS NOT NULL
                  AND route_title != ''
                """,
                (route_date,),
            ).fetchone()[0]

        route_counts[route_date] += 1
        conn.execute(
            "UPDATE assigned_routes SET route_title = ? WHERE id = ?",
            (f"Route {route_counts[route_date]}", route_id),
        )


def next_route_title(conn, route_date):
    route_count = conn.execute(
        "SELECT COUNT(*) FROM assigned_routes WHERE route_date = ?",
        (route_date.isoformat(),),
    ).fetchone()[0]
    return f"Route {route_count + 1}"


def save_route_assignment(route_date, driver, stops, distance_km, duration, maps_url):
    init_routes_db()
    farmer_names = [stop["name"] for stop in stops]

    try:
        with sqlite3.connect(ROUTES_DB_FILE) as conn:
            route_title = next_route_title(conn, route_date)
            conn.execute(
                """
                INSERT INTO assigned_routes (
                    route_title,
                    route_date,
                    driver_name,
                    driver_phone,
                    start_name,
                    end_name,
                    farmer_names_json,
                    google_maps_url,
                    distance_km,
                    duration
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_title,
                    route_date.isoformat(),
                    driver["name"],
                    driver["phone"],
                    DEPOT["name"],
                    DESTINATION["name"],
                    json.dumps(farmer_names),
                    maps_url,
                    distance_km,
                    duration,
                ),
            )
            return route_title
    except sqlite3.Error as e:
        halt(f"Could not save route assignment: {e}")


def load_driver_routes(driver_name, route_date):
    init_routes_db()

    try:
        with sqlite3.connect(ROUTES_DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT *
                FROM assigned_routes
                WHERE driver_name = ? AND route_date = ?
                ORDER BY completed ASC, id ASC
                """,
                (driver_name, route_date.isoformat()),
            ).fetchall()
    except sqlite3.Error as e:
        halt(f"Could not read assigned routes: {e}")

    return [dict(row) for row in rows]


def load_assigned_routes(route_date, driver_name=None):
    init_routes_db()
    params = [route_date.isoformat()]
    driver_filter = ""

    if driver_name:
        driver_filter = "AND driver_name = ?"
        params.append(driver_name)

    try:
        with sqlite3.connect(ROUTES_DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT *
                FROM assigned_routes
                WHERE route_date = ?
                {driver_filter}
                ORDER BY completed ASC, id ASC
                """,
                params,
            ).fetchall()
    except sqlite3.Error as e:
        halt(f"Could not read assigned routes: {e}")

    return [dict(row) for row in rows]


def delete_route(route_id):
    init_routes_db()

    try:
        with sqlite3.connect(ROUTES_DB_FILE) as conn:
            conn.execute("DELETE FROM assigned_routes WHERE id = ?", (route_id,))
    except sqlite3.Error as e:
        halt(f"Could not delete route: {e}")


def update_route_completed(route_id, completed):
    init_routes_db()

    try:
        with sqlite3.connect(ROUTES_DB_FILE) as conn:
            conn.execute(
                "UPDATE assigned_routes SET completed = ? WHERE id = ?",
                (1 if completed else 0, route_id),
            )
    except sqlite3.Error as e:
        halt(f"Could not update route status: {e}")


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


def create_optimized_route(api_key, selected_stops):
    body = {
        "origin": stop_payload(DEPOT),
        "destination": stop_payload(DESTINATION),
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
        halt(f"Google Routes request failed: {e}")

    try:
        data = response.json()
    except ValueError:
        st.error(f"Google returned a non-JSON response. Status code: {response.status_code}")
        st.text(response.text)
        st.stop()
        raise RuntimeError("Google returned a non-JSON response.")

    if response.status_code != 200:
        st.error(f"Google Routes API error. Status code: {response.status_code}")
        st.json(data)
        st.stop()
        raise RuntimeError("Google Routes API error.")

    if "routes" not in data or not data["routes"]:
        st.error("No route returned by Google.")
        st.json(data)
        st.stop()
        raise RuntimeError("No route returned by Google.")

    route = data["routes"][0]
    optimized_indexes = route.get("optimizedIntermediateWaypointIndex", [])
    optimized_stops = (
        [selected_stops[index] for index in optimized_indexes]
        if optimized_indexes
        else selected_stops
    )
    distance_km = route["distanceMeters"] / 1000
    duration = route["duration"]
    maps_url = google_maps_route_url(DEPOT, optimized_stops, DESTINATION)

    return optimized_stops, distance_km, duration, maps_url


def render_route_card(route_title, start_name, end_name, distance_km, duration, completed=False):
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

            .route-card.completed {
                opacity: 0.56;
                filter: grayscale(0.65);
                background: rgba(241, 244, 241, 0.78);
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


def render_add_farmer_form():
    with st.sidebar.expander("Add farmer"):
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


def render_saved_route(route, show_driver=False, allow_completion=False, allow_delete=False):
    is_completed = bool(route["completed"])
    render_route_card(
        route["route_title"],
        route["start_name"],
        route["end_name"],
        route["distance_km"],
        route["duration"],
        completed=is_completed,
    )

    if show_driver:
        st.write(f"Driver: **{route['driver_name']}** | {route['driver_phone']}")

    stops = json.loads(route["farmer_names_json"])
    stop_items = "".join(
        f"<div>{i}. {farmer_name}</div>"
        for i, farmer_name in enumerate(stops, start=1)
    )
    completed_class = " completed" if is_completed else ""
    st.markdown(
        f"""
        <div class="route-stops{completed_class}">
            <strong>Stops</strong>
            {stop_items}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if allow_completion:
        completed = st.checkbox(
            "Route completed",
            value=is_completed,
            key=f"completed_{route['id']}",
        )
        if completed != is_completed:
            update_route_completed(route["id"], completed)
            st.rerun()

    st.link_button(
        "Open route in Google Maps",
        route["google_maps_url"],
    )

    if allow_delete:
        if st.button("Delete route", key=f"delete_{route['id']}", type="secondary"):
            delete_route(route["id"])
            st.success(f"Deleted {route['route_title']}.")
            st.rerun()


def render_assign_routes_page():
    farmers = load_farmers()
    drivers = load_drivers()

    if not farmers:
        st.info("Add at least one farmer before creating a route.")
        return

    farmer_lookup = {
        farmer["farmer_name"]: {
            "name": farmer["farmer_name"],
            "lat": float(farmer["lat"]),
            "lng": float(farmer["lng"]),
        }
        for farmer in farmers
    }
    driver_lookup = {driver["name"]: driver for driver in drivers}

    route_date = st.date_input("Route date", value=date.today())
    driver_name = st.selectbox("Assign to driver", options=list(driver_lookup.keys()))
    selected_names = st.multiselect(
        "Choose farmers to visit",
        options=list(farmer_lookup.keys()),
        placeholder="Select farmers for the route",
    )

    if selected_names:
        st.subheader("Selected farmers")
        for i, name in enumerate(selected_names, start=1):
            st.write(f"{i}. {name}")

    create_route = st.button(
        "Create and assign optimized route",
        disabled=not selected_names or not driver_name,
    )

    if not create_route:
        return

    api_key = load_api_key()
    driver = driver_lookup[driver_name]
    selected_stops = [farmer_lookup[name] for name in selected_names]
    optimized_stops, distance_km, duration, maps_url = create_optimized_route(
        api_key,
        selected_stops,
    )

    route_title = save_route_assignment(
        route_date,
        driver,
        optimized_stops,
        distance_km,
        duration,
        maps_url,
    )

    st.success(
        f"{route_title} assigned to {driver['name']} for {route_date.isoformat()}."
    )
    render_route_card(route_title, DEPOT["name"], DESTINATION["name"], distance_km, duration)

    st.subheader("Optimized stop order")
    for i, stop in enumerate(optimized_stops, start=1):
        st.write(f"{i}. {stop['name']}")

    st.link_button("Open route in Google Maps", maps_url)
    st.code(maps_url, language="text")


def render_assigned_routes_page():
    drivers = load_drivers()
    driver_names = [driver["name"] for driver in drivers]

    route_date = st.date_input("Route date", value=date.today(), key="assigned_date")
    driver_filter = st.selectbox("Driver", options=["All drivers"] + driver_names)
    selected_driver = None if driver_filter == "All drivers" else driver_filter
    routes = load_assigned_routes(route_date, selected_driver)

    if not routes:
        st.info(f"No assigned routes found for {route_date.isoformat()}.")
        return

    st.write(f"Assigned routes for **{route_date.isoformat()}**")

    for route in routes:
        render_saved_route(route, show_driver=True, allow_delete=True)
        st.divider()


def render_manager_page():
    st.subheader("Manager")
    manager_page = st.segmented_control(
        "Manager options",
        options=["Assign routes", "Assigned routes"],
        default="Assign routes",
    )

    if manager_page == "Assign routes":
        render_assign_routes_page()
    else:
        render_assigned_routes_page()


def render_driver_page():
    drivers = load_drivers()
    driver_lookup = {driver["name"]: driver for driver in drivers}

    st.subheader("Driver")

    driver_name = st.selectbox("Select your name", options=list(driver_lookup.keys()))
    route_date = st.date_input("Route date", value=date.today())
    routes = load_driver_routes(driver_name, route_date)

    if not routes:
        st.info(f"No routes booked for {driver_name} on {route_date.isoformat()}.")
        return

    st.write(f"Routes booked for **{driver_name}** on **{route_date.isoformat()}**")

    for route in routes:
        render_saved_route(route, allow_completion=True)
        st.divider()


apply_styles()

_, nav_col = st.columns([0.72, 0.28])
with nav_col:
    page = st.segmented_control(
        "View",
        options=["Manager", "Driver"],
        default="Manager",
        label_visibility="collapsed",
    )

render_header()

with st.sidebar:
    st.header("MilkRun")
    st.caption("Build and assign daily milk collection routes.")

    if page == "Manager":
        render_add_farmer_form()

if page == "Manager":
    render_manager_page()
else:
    render_driver_page()
