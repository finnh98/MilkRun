import json
from datetime import date

import streamlit as st

from app_secrets import load_api_key
from config import DEPOT, DESTINATION
from data_access import (
    add_farmer,
    delete_farmer,
    delete_route,
    find_duplicate_farmer_assignments,
    load_assigned_routes,
    load_driver_routes,
    load_drivers,
    load_farmers,
    parse_stop_statuses,
    save_route_assignment,
    update_farmer,
    update_route_completed,
    update_route_stop_statuses,
)
from google_services import create_optimized_route, geocode_eircode
from styles import render_route_card


def render_saved_route(route, show_driver=False, allow_completion=False, allow_delete=False):
    """Render one saved route and optionally expose driver completion/delete actions."""
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
    completed_class = " completed" if is_completed else ""

    if allow_completion:
        render_stop_status_controls(route, stops, completed_class)
    else:
        render_readonly_stop_statuses(route, stops, completed_class)

    if allow_completion:
        completed = st.checkbox(
            "Route completed",
            value=is_completed,
            key=f"completed_{route['id']}",
        )
        if completed != is_completed:
            update_route_completed(route["id"], completed)
            st.rerun()

    st.link_button("Open route in Google Maps", route["google_maps_url"])

    if allow_delete:
        if st.button("Delete route", key=f"delete_{route['id']}", type="secondary"):
            delete_route(route["id"])
            st.success(f"Deleted {route['route_title']}.")
            st.rerun()


def render_stop_status_controls(route, stops, completed_class):
    """Let a driver mark each stop as Pending, Collected, or Skipped."""
    statuses = parse_stop_statuses(route, stops)
    st.markdown(
        f'<div class="route-stops{completed_class}"><strong>Stops</strong></div>',
        unsafe_allow_html=True,
    )

    status_options = ["Pending", "Collected", "Skipped"]
    updated_statuses = dict(statuses)

    for i, farmer_name in enumerate(stops, start=1):
        current_status = statuses.get(farmer_name, "Pending")
        if current_status not in status_options:
            current_status = "Pending"

        updated_statuses[farmer_name] = st.selectbox(
            f"{i}. {farmer_name}",
            options=status_options,
            index=status_options.index(current_status),
            key=f"stop_status_{route['id']}_{i}_{farmer_name}",
        )

    if updated_statuses != statuses:
        update_route_stop_statuses(route["id"], updated_statuses)
        st.rerun()


def render_readonly_stop_statuses(route, stops, completed_class):
    """Show route stop statuses without editable controls."""
    statuses = parse_stop_statuses(route, stops)
    stop_items = "".join(
        f"<div>{i}. {farmer_name} - {statuses.get(farmer_name, 'Pending')}</div>"
        for i, farmer_name in enumerate(stops, start=1)
    )
    st.markdown(
        f"""
        <div class="route-stops{completed_class}">
            <strong>Stops</strong>
            {stop_items}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_manage_farmers_page():
    """Manager page for viewing, adding, editing, and deleting farmers."""
    farmers = load_farmers()
    farmer_lookup = {farmer["farmer_name"]: farmer for farmer in farmers}

    st.write("Current farmers")
    table_rows = [
        {
            "ID": farmer["id"],
            "Name": farmer["farmer_name"],
            "Phone": farmer.get("phone") or "",
            "Latitude": float(farmer["lat"]),
            "Longitude": float(farmer["lng"]),
        }
        for farmer in farmers
    ]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    render_add_farmer_expander()

    if farmers:
        render_edit_delete_farmer_expander(farmer_lookup)


def render_add_farmer_expander():
    """Collapsed add-farmer form with manual coordinates or Eircode lookup."""
    with st.expander("Add farmer", expanded=False):
        location_method = st.radio(
            "Location",
            options=["Enter latitude/longitude", "Lookup by Eircode"],
            horizontal=True,
            key="add_location_method",
        )

        with st.form("manage_add_farmer"):
            new_name = st.text_input("Farmer name")
            new_phone = st.text_input("Phone number", placeholder="+353 87 000 0000")

            if location_method == "Lookup by Eircode":
                new_eircode = st.text_input("Eircode", placeholder="V94 XXXX")
                new_lat = None
                new_lng = None
            else:
                new_eircode = ""
                new_lat = st.text_input("Latitude", placeholder="52.655568")
                new_lng = st.text_input("Longitude", placeholder="-8.451249")

            submitted = st.form_submit_button("Add farmer")

        if submitted:
            new_lat, new_lng = resolve_farmer_location(
                location_method,
                new_eircode,
                new_lat,
                new_lng,
            )
            if new_lat is None or new_lng is None:
                return

            if not new_name.strip():
                st.error("Farmer name is required.")
                return
            if not new_phone.strip():
                st.error("Phone number is required.")
                return

            add_farmer(new_name.strip(), new_phone.strip(), new_lat, new_lng)
            st.success(f"Added {new_name.strip()}.")
            st.rerun()


def render_edit_delete_farmer_expander(farmer_lookup):
    """Collapsed edit/delete controls for existing farmers."""
    with st.expander("Edit or delete farmer", expanded=False):
        selected_farmer_name = st.selectbox(
            "Choose farmer",
            options=list(farmer_lookup.keys()),
        )
        selected_farmer = farmer_lookup[selected_farmer_name]

        edit_location_method = st.radio(
            "Location",
            options=["Enter latitude/longitude", "Lookup by Eircode"],
            horizontal=True,
            key=f"edit_location_method_{selected_farmer['id']}",
        )

        with st.form("edit_farmer"):
            edit_name = st.text_input("Farmer name", value=selected_farmer["farmer_name"])
            edit_phone = st.text_input("Phone number", value=selected_farmer.get("phone") or "")

            if edit_location_method == "Lookup by Eircode":
                edit_eircode = st.text_input("Eircode", placeholder="V94 XXXX")
                edit_lat = float(selected_farmer["lat"])
                edit_lng = float(selected_farmer["lng"])
            else:
                edit_eircode = ""
                edit_lat = st.number_input(
                    "Latitude",
                    value=float(selected_farmer["lat"]),
                    format="%.6f",
                    key=f"edit_lat_{selected_farmer['id']}",
                )
                edit_lng = st.number_input(
                    "Longitude",
                    value=float(selected_farmer["lng"]),
                    format="%.6f",
                    key=f"edit_lng_{selected_farmer['id']}",
                )

            update_submitted = st.form_submit_button("Save changes")

        if update_submitted:
            edit_lat, edit_lng = resolve_farmer_location(
                edit_location_method,
                edit_eircode,
                edit_lat,
                edit_lng,
            )
            if edit_lat is None or edit_lng is None:
                return

            if not edit_name.strip():
                st.error("Farmer name is required.")
                return
            if not edit_phone.strip():
                st.error("Phone number is required.")
                return

            update_farmer(
                selected_farmer["id"],
                edit_name.strip(),
                edit_phone.strip(),
                edit_lat,
                edit_lng,
            )
            st.success(f"Updated {edit_name.strip()}.")
            st.rerun()

        confirm_delete = st.checkbox(
            f"Confirm delete {selected_farmer_name}",
            key=f"confirm_delete_farmer_{selected_farmer['id']}",
        )
        if st.button("Delete farmer", disabled=not confirm_delete, type="secondary"):
            delete_farmer(selected_farmer["id"])
            st.success(f"Deleted {selected_farmer_name}.")
            st.rerun()


def resolve_farmer_location(location_method, eircode, lat, lng):
    """Return coordinates from either manual inputs or Google Eircode geocoding."""
    if location_method == "Lookup by Eircode":
        if not eircode.strip():
            st.error("Eircode is required.")
            return None, None
        return geocode_eircode(eircode.strip(), load_api_key())

    try:
        return float(lat), float(lng)
    except ValueError:
        st.error("Latitude and longitude must be valid numbers.")
        return None, None


def render_assign_routes_page():
    """Manager page for creating optimized routes and assigning them to drivers."""
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

    acknowledge_duplicates = render_duplicate_warning(route_date, selected_names)

    create_route = st.button(
        "Create and assign optimized route",
        disabled=not selected_names or not driver_name or not acknowledge_duplicates,
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


def render_duplicate_warning(route_date, selected_names):
    """Warn managers before creating routes with farmers already assigned that day."""
    duplicate_assignments = find_duplicate_farmer_assignments(route_date, selected_names)
    if not duplicate_assignments:
        return True

    duplicate_lines = [
        f"{item['farmer_name']} is already on {item['route_title']} "
        f"for {item['driver_name']}."
        for item in duplicate_assignments
    ]
    st.warning(
        "Some selected farmers are already assigned on this date:\n\n"
        + "\n".join(f"- {line}" for line in duplicate_lines)
    )
    return st.checkbox(
        "I understand and want to create another route with these farmers",
        key="acknowledge_duplicate_farmers",
    )


def render_assigned_routes_page():
    """Manager page for reviewing and deleting assigned routes."""
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
    """Top-level manager workflow with route assignment, review, and farmer admin."""
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
    """Driver workflow for viewing routes and updating collection progress."""
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
