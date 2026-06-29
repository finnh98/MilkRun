import sqlite3
from pathlib import Path


DB_FILE = Path(__file__).resolve().parent / "farmers.db"


def main():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Database not found: {DB_FILE}")

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, farmer_name, phone, lat, lng FROM farmers ORDER BY farmer_name"
        ).fetchall()

    if not rows:
        print("No farmers found.")
        return

    print(f"Farmers in {DB_FILE.name}:")
    for row in rows:
        print(
            f"{row['id']:>3} | {row['farmer_name']} | {row['phone']} | "
            f"{row['lat']:.12f} | {row['lng']:.12f}"
        )


if __name__ == "__main__":
    main()
