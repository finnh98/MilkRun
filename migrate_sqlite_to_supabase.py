import json
import sqlite3
from pathlib import Path

from supabase import create_client


BASE_DIR = Path(__file__).resolve().parent
SUPABASE_FILE = BASE_DIR / "supabase_detail.json"


def load_supabase_client():
    config = json.loads(SUPABASE_FILE.read_text())
    supabase_url = config.get("supabase_url") or config.get("project_url")
    supabase_key = config.get("supabase_key")

    if not supabase_url or not supabase_key:
        raise RuntimeError("supabase_detail.json must contain project_url/supabase_url and supabase_key.")

    return create_client(supabase_url, supabase_key)


def sqlite_rows(db_name, query):
    with sqlite3.connect(BASE_DIR / db_name) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query).fetchall()]


def migrate_farmers(supabase):
    rows = sqlite_rows(
        "farmers.db",
        "SELECT id, farmer_name, phone, lat, lng FROM farmers ORDER BY id",
    )
    if rows:
        supabase.table("farmers").upsert(rows).execute()
    print(f"Migrated {len(rows)} farmers.")


def migrate_drivers(supabase):
    rows = sqlite_rows(
        "drivers.db",
        "SELECT id, name, phone FROM drivers ORDER BY id",
    )
    if rows:
        supabase.table("drivers").upsert(rows).execute()
    print(f"Migrated {len(rows)} drivers.")


def migrate_routes(supabase):
    rows = sqlite_rows(
        "routes.db",
        """
        SELECT
            id,
            route_title,
            route_date,
            driver_name,
            driver_phone,
            start_name,
            end_name,
            farmer_names_json,
            google_maps_url,
            distance_km,
            duration,
            completed,
            created_at
        FROM assigned_routes
        ORDER BY id
        """,
    )
    for row in rows:
        row["completed"] = bool(row["completed"])

    if rows:
        supabase.table("assigned_routes").upsert(rows).execute()
    print(f"Migrated {len(rows)} assigned routes.")


def main():
    supabase = load_supabase_client()
    migrate_farmers(supabase)
    migrate_drivers(supabase)
    migrate_routes(supabase)


if __name__ == "__main__":
    main()
