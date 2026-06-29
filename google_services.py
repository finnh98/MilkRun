from urllib.parse import urlencode

import requests
import streamlit as st

from app_secrets import halt
from config import DEPOT, DESTINATION


def stop_payload(stop):
    """Convert an app stop dict into the Google Routes API location shape."""
    return {
        "location": {
            "latLng": {
                "latitude": float(stop["lat"]),
                "longitude": float(stop["lng"]),
            }
        }
    }


def maps_location(stop):
    """Convert a stop into the lat,lng text used in Google Maps URLs."""
    return f"{stop['lat']},{stop['lng']}"


def google_maps_route_url(origin, stops, destination):
    """Build a Google Maps multi-stop directions URL for drivers to open."""
    params = {
        "api": "1",
        "origin": maps_location(origin),
        "destination": maps_location(destination),
        "travelmode": "driving",
    }

    if stops:
        params["waypoints"] = "|".join(maps_location(stop) for stop in stops)

    return "https://www.google.com/maps/dir/?" + urlencode(params)


def geocode_eircode(eircode, api_key):
    """Use Google Geocoding to convert an Irish Eircode into coordinates."""
    params = {
        "address": f"{eircode}, Ireland",
        "region": "ie",
        "key": api_key,
    }

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=20,
        )
    except requests.RequestException as e:
        halt(f"Google Geocoding request failed: {e}")

    try:
        data = response.json()
    except ValueError:
        st.error(f"Google returned a non-JSON response. Status code: {response.status_code}")
        st.text(response.text)
        st.stop()
        raise RuntimeError("Google returned a non-JSON response.")

    if data.get("status") != "OK" or not data.get("results"):
        error_message = data.get("error_message") or data.get("status") or "No result found."
        halt(f"Could not geocode Eircode: {error_message}")

    location = data["results"][0]["geometry"]["location"]
    return float(location["lat"]), float(location["lng"])


def create_optimized_route(api_key, selected_stops):
    """Ask Google Routes for optimized waypoint order and route metrics."""
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
