from pathlib import Path


# Shared file paths and fixed route endpoints used throughout the app.
BASE_DIR = Path(__file__).resolve().parent
API_KEY_FILE = BASE_DIR / "maps_api_key.json"
SUPABASE_FILE = BASE_DIR / "supabase_detail.json"
LOGO_FILE = BASE_DIR / "milkrun_logo.png"


# Every generated route starts at Treaty County Trucking.
DEPOT = {
    "name": "Treaty County Trucking",
    "lat": 52.6555680292862,
    "lng": -8.451248793153795,
}


# Every generated route finishes at Kerry Processing Plant.
DESTINATION = {
    "name": "Kerry Processing Plant, Charleville",
    "lat": 52.35922556999083,
    "lng": -8.672190576960151,
}
