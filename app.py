import base64
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st
import requests
from supabase import create_client
from streamlit.errors import StreamlitSecretNotFoundError


BASE_DIR = Path(__file__).resolve().parent
API_KEY_FILE = BASE_DIR / "maps_api_key.json"
SUPABASE_FILE = BASE_DIR / "supabase_detail.json"
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

DEFAULT_FARMER_PHONES = {
    "Andrew Egan": "+353 87 410 1123",
    "Ballyneety Farmer A": "+353 86 420 3344",
    "Caherline Farmer A": "+353 85 430 5566",
    "Hospital Farmer A": "+353 87 440 7788",
    "Hospital Farmer B": "+353 86 450 9900",
    "John Hourigan": "+353 85 460 1212",
    "Kilteely Farmer A": "+353 87 470 3434",
    "Paul Keane": "+353 86 480 5656",
}


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


def load_supabase_config():
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
    supabase_url, supabase_key = load_supabase_config()
    return create_client(supabase_url, supabase_key)


def supabase_error(message, error):
    halt(f"{message}: {error}")


def load_farmers():
    try:
        response = (
            get_supabase_client()
            .table("farmers")
            .select("farmer_name, phone, lat, lng")
            .order("farmer_name")
            .execute()
        )
    except Exception as e:
        supabase_error("Could not read farmers from Supabase", e)

    return response.data or []


def add_farmer(name, phone, lat, lng):
    try:
        get_supabase_client().table("farmers").insert(
            {
                "farmer_name": name,
                "phone": phone,
                "lat": float(lat),
                "lng": float(lng),
            }
        ).execute()
    except Exception as e:
        supabase_error("Could not add farmer to Supabase", e)


def load_drivers():
    try:
        response = (
            get_supabase_client()
            .table("drivers")
            .select("name, phone")
            .order("name")
            .execute()
        )
    except Exception as e:
        supabase_error("Could not read drivers from Supabase", e)

    return response.data or []


def next_route_title(route_date):
    try:
        response = (
            get_supabase_client()
            .table("assigned_routes")
            .select("id")
            .eq("route_date", route_date.isoformat())
            .execute()
        )
    except Exception as e:
        supabase_error("Could not count assigned routes in Supabase", e)

    return f"Route {len(response.data or []) + 1}"


def save_route_assignment(route_date, driver, stops, distance_km, duration, maps_url):
    farmer_names = [stop["name"] for stop in stops]
    route_title = next_route_title(route_date)

    try:
        get_supabase_client().table("assigned_routes").insert(
            {
                "route_title": route_title,
                "route_date": route_date.isoformat(),
                "driver_name": driver["name"],
                "driver_phone": driver["phone"],
                "start_name": DEPOT["name"],
                "end_name": DESTINATION["name"],
                "farmer_names_json": json.dumps(farmer_names),
                "google_maps_url": maps_url,
                "distance_km": float(distance_km),
                "duration": duration,
                "completed": False,
            }
        ).execute()
    except Exception as e:
        supabase_error("Could not save route assignment to Supabase", e)

    return route_title


def load_driver_routes(driver_name, route_date):
    try:
        response = (
            get_supabase_client()
            .table("assigned_routes")
            .select("*")
            .eq("driver_name", driver_name)
            .eq("route_date", route_date.isoformat())
            .order("completed")
            .order("id")
            .execute()
        )
    except Exception as e:
        supabase_error("Could not read driver routes from Supabase", e)

    return response.data or []


def load_assigned_routes(route_date, driver_name=None):
    try:
        query = (
            get_supabase_client()
            .table("assigned_routes")
            .select("*")
            .eq("route_date", route_date.isoformat())
        )
        if driver_name:
            query = query.eq("driver_name", driver_name)
        response = query.order("completed").order("id").execute()
    except Exception as e:
        supabase_error("Could not read assigned routes from Supabase", e)

    return response.data or []


def delete_route(route_id):
    try:
        get_supabase_client().table("assigned_routes").delete().eq("id", route_id).execute()
    except Exception as e:
        supabase_error("Could not delete route from Supabase", e)


def update_route_completed(route_id, completed):
    try:
        get_supabase_client().table("assigned_routes").update(
            {"completed": bool(completed)}
        ).eq("id", route_id).execute()
    except Exception as e:
        supabase_error("Could not update route status in Supabase", e)


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


def render_manage_farmers_page():
    farmers = load_farmers()

    st.write("Current farmers")
    table_rows = [
        {
            "Name": farmer["farmer_name"],
            "Phone": farmer.get("phone") or "",
            "Latitude": float(farmer["lat"]),
            "Longitude": float(farmer["lng"]),
        }
        for farmer in farmers
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    st.subheader("Add farmer")
    with st.form("manage_add_farmer"):
        new_name = st.text_input("Farmer name")
        new_phone = st.text_input("Phone number", placeholder="+353 87 000 0000")
        new_lat = st.number_input("Latitude", value=53.3498, format="%.6f")
        new_lng = st.number_input("Longitude", value=-6.2603, format="%.6f")
        submitted = st.form_submit_button("Add farmer")

    if submitted:
        if not new_name.strip():
            st.error("Farmer name is required.")
            return
        if not new_phone.strip():
            st.error("Phone number is required.")
            return

        add_farmer(new_name.strip(), new_phone.strip(), new_lat, new_lng)
        st.success(f"Added {new_name.strip()}.")
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
        options=["Assign routes", "Assigned routes", "Manage Farmers"],
        default="Assign routes",
    )

    if manager_page == "Assign routes":
        render_assign_routes_page()
    elif manager_page == "Assigned routes":
        render_assigned_routes_page()
    else:
        render_manage_farmers_page()


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
    render_manager_page()
else:
    render_driver_page()
