import json

from app_secrets import get_supabase_client, supabase_error
from config import DEPOT, DESTINATION


def load_farmers():
    """Read farmer records from Supabase for tables, editing, and route selection."""
    try:
        response = (
            get_supabase_client()
            .table("farmers")
            .select("id, farmer_name, phone, lat, lng")
            .order("farmer_name")
            .execute()
        )
    except Exception as e:
        supabase_error("Could not read farmers from Supabase", e)

    return response.data or []


def add_farmer(name, phone, lat, lng):
    """Insert a new farmer into Supabase."""
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


def update_farmer(farmer_id, name, phone, lat, lng):
    """Update an existing farmer's contact details and coordinates."""
    try:
        get_supabase_client().table("farmers").update(
            {
                "farmer_name": name,
                "phone": phone,
                "lat": float(lat),
                "lng": float(lng),
            }
        ).eq("id", farmer_id).execute()
    except Exception as e:
        supabase_error("Could not update farmer in Supabase", e)


def delete_farmer(farmer_id):
    """Delete a farmer record from Supabase."""
    try:
        get_supabase_client().table("farmers").delete().eq("id", farmer_id).execute()
    except Exception as e:
        supabase_error("Could not delete farmer from Supabase", e)


def load_drivers():
    """Read the current driver list from Supabase."""
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
    """Generate Route 1, Route 2, etc. for the selected date."""
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


def initial_stop_statuses(stops):
    """Create the default per-farmer status map for a new route."""
    return {stop["name"]: "Pending" for stop in stops}


def parse_stop_statuses(route, stops):
    """Read saved stop statuses and backfill missing stops as Pending."""
    raw_statuses = route.get("stop_statuses_json")

    if raw_statuses:
        try:
            statuses = json.loads(raw_statuses)
        except json.JSONDecodeError:
            statuses = {}
    else:
        statuses = {}

    for stop in stops:
        statuses.setdefault(stop, "Pending")

    return statuses


def save_route_assignment(route_date, driver, stops, distance_km, duration, maps_url):
    """Persist a newly optimized route assignment in Supabase."""
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
                "stop_statuses_json": json.dumps(initial_stop_statuses(stops)),
                "completed": False,
            }
        ).execute()
    except Exception as e:
        supabase_error("Could not save route assignment to Supabase", e)

    return route_title


def load_driver_routes(driver_name, route_date):
    """Load routes assigned to one driver on one date."""
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
    """Load assigned routes for manager review, optionally filtered by driver."""
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
    """Delete an assigned route from Supabase."""
    try:
        get_supabase_client().table("assigned_routes").delete().eq("id", route_id).execute()
    except Exception as e:
        supabase_error("Could not delete route from Supabase", e)


def update_route_completed(route_id, completed):
    """Toggle the whole-route completed state."""
    try:
        get_supabase_client().table("assigned_routes").update(
            {"completed": bool(completed)}
        ).eq("id", route_id).execute()
    except Exception as e:
        supabase_error("Could not update route status in Supabase", e)


def update_route_stop_statuses(route_id, stop_statuses):
    """Save per-farmer stop statuses for a driver's route."""
    try:
        get_supabase_client().table("assigned_routes").update(
            {"stop_statuses_json": json.dumps(stop_statuses)}
        ).eq("id", route_id).execute()
    except Exception as e:
        supabase_error("Could not update stop statuses in Supabase", e)


def find_duplicate_farmer_assignments(route_date, selected_names):
    """Find selected farmers already assigned to another route on the same date."""
    if not selected_names:
        return []

    selected = set(selected_names)
    duplicates = []

    for route in load_assigned_routes(route_date):
        try:
            route_farmers = json.loads(route["farmer_names_json"])
        except json.JSONDecodeError:
            route_farmers = []

        for farmer_name in route_farmers:
            if farmer_name in selected:
                duplicates.append(
                    {
                        "farmer_name": farmer_name,
                        "route_title": route["route_title"],
                        "driver_name": route["driver_name"],
                    }
                )

    return duplicates
