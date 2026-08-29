"""JSON -> SQLite at boot (Decision 007). The .db is a rebuildable artifact,
never committed; properties.json / rates.json / inventory.json / addons.json
are the source of truth and live in git.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE properties (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    area TEXT,
    lat REAL,
    lng REAL,
    type TEXT NOT NULL,
    star_tier INTEGER NOT NULL,
    description TEXT NOT NULL,
    amenities_json TEXT NOT NULL,
    images_json TEXT NOT NULL,
    check_in_time TEXT NOT NULL,
    check_out_time TEXT NOT NULL
);
CREATE INDEX idx_properties_city ON properties(city);

CREATE TABLE room_types (
    id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL REFERENCES properties(id),
    name TEXT NOT NULL,
    base_occupancy INTEGER NOT NULL,
    max_occupancy INTEGER NOT NULL,
    max_adults INTEGER NOT NULL,
    max_children INTEGER NOT NULL,
    extra_bed_allowed INTEGER NOT NULL,
    extra_bed_price REAL,
    bed_config TEXT NOT NULL,
    size_sqft INTEGER,
    view TEXT NOT NULL,
    amenities_json TEXT NOT NULL,
    units_total INTEGER NOT NULL
);
CREATE INDEX idx_room_types_property ON room_types(property_id);

CREATE TABLE policies (
    property_id TEXT NOT NULL REFERENCES properties(id),
    key TEXT NOT NULL,
    status TEXT NOT NULL,
    value_json TEXT,
    source TEXT,
    PRIMARY KEY (property_id, key)
);

CREATE TABLE rates (
    room_type_id TEXT NOT NULL REFERENCES room_types(id),
    date TEXT NOT NULL,
    price REAL NOT NULL,
    min_stay INTEGER NOT NULL,
    closed_to_arrival INTEGER NOT NULL,
    PRIMARY KEY (room_type_id, date)
);
CREATE INDEX idx_rates_room_date ON rates(room_type_id, date);

CREATE TABLE inventory (
    room_type_id TEXT NOT NULL REFERENCES room_types(id),
    date TEXT NOT NULL,
    units_available INTEGER NOT NULL,
    PRIMARY KEY (room_type_id, date)
);
CREATE INDEX idx_inventory_room_date ON inventory(room_type_id, date);

CREATE TABLE addons (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    property_id TEXT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    price_basis TEXT NOT NULL,
    eligibility TEXT,
    segment_affinity_json TEXT NOT NULL
);
CREATE INDEX idx_addons_property ON addons(property_id);
"""


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def build_database(data_dir: Path, sqlite_path: Path) -> sqlite3.Connection:
    """Load the JSON dataset into a fresh SQLite DB at sqlite_path and return
    an open connection. Overwrites any existing DB at that path.
    """
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()

    conn = sqlite3.connect(sqlite_path)
    conn.executescript(SCHEMA)

    catalogue = _read_json(data_dir / "properties.json")
    rates = _read_json(data_dir / "rates.json")
    inventory = _read_json(data_dir / "inventory.json")
    addons = _read_json(data_dir / "addons.json")

    conn.execute("INSERT INTO meta VALUES (?, ?)", ("demo_today", catalogue["demo_today"]))
    conn.execute("INSERT INTO meta VALUES (?, ?)", ("window_days", str(catalogue["window_days"])))
    conn.execute("INSERT INTO meta VALUES (?, ?)", ("tax_rule_json", json.dumps(catalogue["tax_rule"])))

    for p in catalogue["properties"]:
        geo = p.get("geo") or {}
        conn.execute(
            "INSERT INTO properties VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p["id"], p["name"], p["city"], p.get("area"), geo.get("lat"), geo.get("lng"),
             p["type"], p["star_tier"], p["description"], json.dumps(p["amenities"]),
             json.dumps(p["images"]), p["check_in_time"], p["check_out_time"]),
        )
        for r in p["room_types"]:
            conn.execute(
                "INSERT INTO room_types VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["id"], r["property_id"], r["name"], r["base_occupancy"], r["max_occupancy"],
                 r["max_adults"], r["max_children"], int(r["extra_bed_allowed"]), r["extra_bed_price"],
                 r["bed_config"], r["size_sqft"], r["view"], json.dumps(r["amenities"]), r["units_total"]),
            )
        for pol in p["policies"]:
            pv = pol["policy"]
            conn.execute(
                "INSERT INTO policies VALUES (?,?,?,?,?)",
                (pol["property_id"], pol["key"], pv["status"],
                 json.dumps(pv["value"]) if pv["value"] is not None else None, pv.get("source")),
            )

    for r in rates:
        conn.execute(
            "INSERT INTO rates VALUES (?,?,?,?,?)",
            (r["room_type_id"], r["date"], r["price"], r["min_stay"], int(r["closed_to_arrival"])),
        )
    for inv in inventory:
        conn.execute(
            "INSERT INTO inventory VALUES (?,?,?)",
            (inv["room_type_id"], inv["date"], inv["units_available"]),
        )
    for a in addons:
        conn.execute(
            "INSERT INTO addons VALUES (?,?,?,?,?,?,?,?,?)",
            (a["id"], a["scope"], a.get("property_id"), a["category"], a["name"], a["price"],
             a["price_basis"], a.get("eligibility"), json.dumps(a["segment_affinity"])),
        )

    conn.commit()
    return conn
