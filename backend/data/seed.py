"""Seeded dataset generator (Decision 006/007).

Produces backend/data/properties.json, rates.json, inventory.json, addons.json.
Deterministic given SEED — re-running produces byte-identical output. JSON is
the source of truth and is committed to git; SQLite is built from it at boot
and never committed.

24 properties across 8 cities. 16 generated here programmatically; 8
hand-authored in Goa, each planting exactly one edge case (plan §8 / §12):

  1. date_shift        — booked out for the demo window, opens exactly +2 days later
  2. unknown_info       — pool_heated is genuinely unknown, not false
  3. policy_conflict    — strictly non-smoking, no smoking rooms at all
  4. capacity_conflict  — single room type capped at 2 guests
  5. capacity_split     — one villa room type sleeping 8
  6. price_cliff        — sharp seasonal price jump mid-window
  7. min_stay           — 3-night minimum stay enforced
  8. fully_booked       — zero inventory across the entire demo window
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
DATA_DIR = Path(__file__).resolve().parent

# Anchor "today" for the seeded demo window. Deterministic and decoupled from
# wall-clock time; the app's `today_override` setting points at this for demos.
DEMO_TODAY = date(2026, 9, 2)  # Wednesday
WINDOW_DAYS = 21  # DEMO_TODAY .. DEMO_TODAY + 20, covers "this/next weekend"

CITIES = {
    "Goa": {"lat": 15.2993, "lng": 74.1240, "areas": ["Candolim", "Anjuna", "Baga", "Palolem", "Panjim"]},
    "Jaipur": {"lat": 26.9124, "lng": 75.7873, "areas": ["Amer", "C-Scheme", "Malviya Nagar"]},
    "Udaipur": {"lat": 24.5854, "lng": 73.7125, "areas": ["Lake Pichola", "Fatehsagar"]},
    "Rishikesh": {"lat": 30.0869, "lng": 78.2676, "areas": ["Tapovan", "Laxman Jhula"]},
    "Manali": {"lat": 32.2432, "lng": 77.1892, "areas": ["Old Manali", "Vashisht"]},
    "Coorg": {"lat": 12.3375, "lng": 75.8069, "areas": ["Madikeri", "Virajpet"]},
    "Lonavala": {"lat": 18.7546, "lng": 73.4062, "areas": ["Tungarli", "Old Lonavala"]},
    "Alibaug": {"lat": 18.6414, "lng": 72.8722, "areas": ["Nagaon", "Kihim"]},
}

PROPERTY_TYPES = ["hotel", "resort", "villa", "homestay", "guesthouse", "boutique"]
BED_CONFIGS = ["king", "twin", "queen", "bunk"]
VIEWS = ["sea", "pool", "garden", "mountain", "city", "none"]

AMENITY_POOL = [
    "wifi", "pool", "parking", "restaurant", "bar", "spa", "gym", "beach_access",
    "airport_shuttle", "room_service", "power_backup", "pet_friendly_common_areas",
    "bonfire", "board_games", "bicycle_rental", "kids_play_area",
]
ROOM_AMENITY_POOL = ["ac", "tv", "minibar", "balcony", "bathtub", "workdesk", "coffee_maker"]

NAME_PREFIXES = ["The", "Casa", "Villa", "Amber", "Blue", "Green", "Golden", "Silver", "Sunset", "Riverside"]
NAME_NOUNS = ["Retreat", "Residency", "Nest", "Cottage", "Manor", "Grove", "Haven", "Bay", "Springs", "Court"]

TAX_RULE = {
    "slabs": [
        {"max_per_night_rate": 7500.0, "gst_percent": 12.0},
        {"max_per_night_rate": None, "gst_percent": 18.0},
    ],
    "fixed_fee_per_stay": 250.0,
}


def daterange(start: date, days: int):
    for i in range(days):
        yield start + timedelta(days=i)


def make_room_type(rng: random.Random, prop_id: str, idx: int, *, force=None) -> dict:
    force = force or {}
    base_occ = force.get("base_occupancy", rng.choice([1, 2, 2, 2, 3]))
    max_occ = force.get("max_occupancy", base_occ + rng.choice([0, 1, 2]))
    max_adults = force.get("max_adults", max_occ)
    max_children = force.get("max_children", max(0, max_occ - max_adults + 1) if max_occ > max_adults else 1)
    return {
        "id": f"{prop_id}-rt{idx}",
        "property_id": prop_id,
        "name": force.get("name", rng.choice(["Deluxe Room", "Superior Room", "Garden Suite", "Premium Suite", "Cottage"])),
        "base_occupancy": base_occ,
        "max_occupancy": max_occ,
        "max_adults": max_adults,
        "max_children": max_children,
        "extra_bed_allowed": force.get("extra_bed_allowed", max_occ > base_occ),
        "extra_bed_price": force.get("extra_bed_price", 1200.0 if max_occ > base_occ else None),
        "bed_config": force.get("bed_config", rng.choice(BED_CONFIGS)),
        "size_sqft": force.get("size_sqft", rng.randint(220, 650)),
        "view": force.get("view", rng.choice(VIEWS)),
        "amenities": force.get("amenities", sorted(rng.sample(ROOM_AMENITY_POOL, k=rng.randint(2, 4)))),
        "units_total": force.get("units_total", rng.randint(2, 6)),
    }


def make_rates_and_inventory(rng: random.Random, room: dict, base_price: float, *, price_cliff_on: date | None = None,
                              min_stay: int = 1, zero_from: date | None = None, zero_until: date | None = None) -> tuple[list[dict], list[dict]]:
    rates, inventory = [], []
    for d in daterange(DEMO_TODAY, WINDOW_DAYS):
        price = base_price
        if price_cliff_on is not None and d >= price_cliff_on:
            price = base_price * 2.4
        elif d.weekday() in (4, 5):  # Fri/Sat night premium
            price = base_price * 1.15
        price = round(price / 50) * 50
        rates.append({
            "room_type_id": room["id"], "date": d.isoformat(), "price": price,
            "min_stay": min_stay, "closed_to_arrival": False,
        })
        units = room["units_total"]
        if zero_from is not None and zero_from <= d < (zero_until or date.max):
            units = 0
        else:
            units = max(0, units - rng.randint(0, max(0, room["units_total"] - 1)))
        inventory.append({"room_type_id": room["id"], "date": d.isoformat(), "units_available": units})
    return rates, inventory


def policy_known(prop_id: str, key: str, value, source="listed") -> dict:
    return {"property_id": prop_id, "key": key, "policy": {"status": "known", "value": value, "source": source}}


def policy_unknown(prop_id: str, key: str) -> dict:
    return {"property_id": prop_id, "key": key, "policy": {"status": "unknown", "value": None, "source": None}}


def policy_na(prop_id: str, key: str) -> dict:
    return {"property_id": prop_id, "key": key, "policy": {"status": "not_applicable", "value": None, "source": None}}


def default_policies(prop_id: str, rng: random.Random) -> list[dict]:
    return [
        policy_known(prop_id, "smoking", rng.choice([True, False])),
        policy_known(prop_id, "pets", rng.choice([True, False])),
        policy_known(prop_id, "early_checkin", rng.choice([True, False, "on_request"])),
        policy_known(prop_id, "late_checkout", rng.choice([True, False, "on_request"])),
        policy_known(prop_id, "party_friendly", rng.choice([True, False])),
        policy_known(prop_id, "pool_heated", rng.choice([True, False])) if rng.random() > 0.3 else policy_unknown(prop_id, "pool_heated"),
    ]


def generate_property(rng: random.Random, city: str, seq: int) -> tuple[dict, list[dict], list[dict], list[dict], list[dict]]:
    prop_id = f"{city.lower()}-gen-{seq:02d}"
    meta = CITIES[city]
    ptype = rng.choice(PROPERTY_TYPES)
    name = f"{rng.choice(NAME_PREFIXES)} {rng.choice(NAME_NOUNS)}"
    amenities = sorted(rng.sample(AMENITY_POOL, k=rng.randint(4, 8)))
    prop = {
        "id": prop_id, "name": name, "city": city, "area": rng.choice(meta["areas"]),
        "geo": {"lat": meta["lat"] + rng.uniform(-0.05, 0.05), "lng": meta["lng"] + rng.uniform(-0.05, 0.05)},
        "type": ptype, "star_tier": rng.choice([3, 3, 4, 4, 5]),
        "description": f"A {ptype} in {rng.choice(meta['areas'])}, {city}, with {amenities[0].replace('_', ' ')} and more.",
        "amenities": amenities, "images": [],
        "check_in_time": "14:00", "check_out_time": "11:00",
    }
    n_rooms = rng.randint(2, 5)
    rooms, rates, inventory = [], [], []
    base_prices = sorted(rng.sample(range(2500, 14000, 250), k=n_rooms))
    for i in range(n_rooms):
        room = make_room_type(rng, prop_id, i + 1)
        rooms.append(room)
        r, inv = make_rates_and_inventory(rng, room, float(base_prices[i]))
        rates += r
        inventory += inv
    policies = default_policies(prop_id, rng)
    return prop, rooms, rates, inventory, policies


def edge_case_properties(rng: random.Random) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    props, rooms_all, rates_all, inv_all, policies_all = [], [], [], [], []
    city = "Goa"
    meta = CITIES[city]

    def base(prop_id, name, area, ptype="villa", star=4):
        return {
            "id": prop_id, "name": name, "city": city, "area": area,
            "geo": {"lat": meta["lat"] + rng.uniform(-0.05, 0.05), "lng": meta["lng"] + rng.uniform(-0.05, 0.05)},
            "type": ptype, "star_tier": star, "description": f"{name}, {area}, Goa.",
            "amenities": sorted(rng.sample(AMENITY_POOL, k=6)), "images": [],
            "check_in_time": "14:00", "check_out_time": "11:00",
        }

    # 1. date_shift — booked out for the demo window, opens exactly +2 days later
    pid = "goa-edge-dateshift"
    props.append(base(pid, "Tidewatch Villa", "Candolim"))
    room = make_room_type(rng, pid, 1, force={"name": "Sea View Room", "units_total": 4})
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 6000.0, zero_from=DEMO_TODAY, zero_until=DEMO_TODAY + timedelta(days=2))
    rates_all += r; inv_all += inv
    policies_all += default_policies(pid, rng)

    # 2. unknown_info — pool_heated genuinely unknown
    pid = "goa-edge-unknown"
    props.append(base(pid, "Palm Grove Homestay", "Anjuna", ptype="homestay", star=3))
    room = make_room_type(rng, pid, 1, force={"name": "Garden Room", "units_total": 5})
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 4200.0)
    rates_all += r; inv_all += inv
    policies_all += [
        policy_unknown(pid, "pool_heated"),
        policy_known(pid, "smoking", False), policy_known(pid, "pets", True),
        policy_known(pid, "early_checkin", "on_request"), policy_known(pid, "late_checkout", "on_request"),
        policy_known(pid, "party_friendly", False),
    ]

    # 3. policy_conflict — strictly non-smoking, no exceptions
    pid = "goa-edge-nosmoking"
    props.append(base(pid, "Whitesands Boutique", "Palolem", ptype="boutique", star=4))
    room = make_room_type(rng, pid, 1, force={"name": "Deluxe Room", "units_total": 5})
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 5500.0)
    rates_all += r; inv_all += inv
    policies_all += [
        policy_known(pid, "smoking", False, source="strict, no exceptions"),
        policy_known(pid, "pets", False), policy_known(pid, "early_checkin", False),
        policy_known(pid, "late_checkout", "on_request"), policy_known(pid, "party_friendly", False),
        policy_known(pid, "pool_heated", False),
    ]

    # 4. capacity_conflict — single room type capped at 2 guests
    pid = "goa-edge-cap2"
    props.append(base(pid, "Cove Corner Guesthouse", "Baga", ptype="guesthouse", star=3))
    room = make_room_type(rng, pid, 1, force={
        "name": "Cozy Double", "base_occupancy": 2, "max_occupancy": 2, "max_adults": 2,
        "max_children": 0, "extra_bed_allowed": False, "extra_bed_price": None, "units_total": 6,
    })
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 3200.0)
    rates_all += r; inv_all += inv
    policies_all += default_policies(pid, rng)

    # 5. capacity_split — villa sleeping 8
    pid = "goa-edge-villa8"
    props.append(base(pid, "Grand Dunes Villa", "Candolim", ptype="villa", star=5))
    room = make_room_type(rng, pid, 1, force={
        "name": "Entire Villa (4BHK)", "base_occupancy": 6, "max_occupancy": 8, "max_adults": 8,
        "max_children": 4, "extra_bed_allowed": True, "extra_bed_price": 1500.0, "units_total": 2,
    })
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 18000.0)
    rates_all += r; inv_all += inv
    policies_all += default_policies(pid, rng)

    # 6. price_cliff — sharp seasonal jump mid-window
    pid = "goa-edge-pricecliff"
    props.append(base(pid, "Amber Coast Resort", "Anjuna", ptype="resort", star=4))
    room = make_room_type(rng, pid, 1, force={"name": "Pool View Room", "units_total": 6})
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 5000.0, price_cliff_on=DEMO_TODAY + timedelta(days=10))
    rates_all += r; inv_all += inv
    policies_all += default_policies(pid, rng)

    # 7. min_stay — 3-night minimum
    pid = "goa-edge-minstay3"
    props.append(base(pid, "Riverside Manor", "Panjim", ptype="hotel", star=4))
    room = make_room_type(rng, pid, 1, force={"name": "Superior Room", "units_total": 5})
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 4800.0, min_stay=3)
    rates_all += r; inv_all += inv
    policies_all += default_policies(pid, rng)

    # 8. fully_booked — zero inventory across the entire demo window
    pid = "goa-edge-fullybooked"
    props.append(base(pid, "The Golden Bay Resort", "Baga", ptype="resort", star=5))
    room = make_room_type(rng, pid, 1, force={"name": "Premium Suite", "units_total": 4})
    rooms_all.append(room)
    r, inv = make_rates_and_inventory(rng, room, 9000.0, zero_from=DEMO_TODAY, zero_until=DEMO_TODAY + timedelta(days=WINDOW_DAYS))
    rates_all += r; inv_all += inv
    policies_all += default_policies(pid, rng)

    return props, rooms_all, rates_all, inv_all, policies_all


def generate_addons(properties: list[dict]) -> list[dict]:
    addons = [
        {"id": "addon-airport-pickup", "scope": "global", "property_id": None, "category": "transport",
         "name": "Airport Pickup", "price": 1500.0, "price_basis": "per_stay",
         "eligibility": "requires_airport", "segment_affinity": ["couple", "family_with_kids", "solo"]},
        {"id": "addon-breakfast", "scope": "global", "property_id": None, "category": "food",
         "name": "Daily Breakfast", "price": 450.0, "price_basis": "per_person",
         "eligibility": None, "segment_affinity": ["family_with_kids", "extended_family"]},
        {"id": "addon-early-checkin", "scope": "global", "property_id": None, "category": "room_upgrade",
         "name": "Guaranteed Early Check-in", "price": 1000.0, "price_basis": "per_stay",
         "eligibility": "requires_early_checkin_available", "segment_affinity": ["business", "workation"]},
        {"id": "addon-late-checkout", "scope": "global", "property_id": None, "category": "room_upgrade",
         "name": "Guaranteed Late Checkout", "price": 1000.0, "price_basis": "per_stay",
         "eligibility": "requires_late_checkout_available", "segment_affinity": ["leisure"]},
        {"id": "addon-candlelight-dinner", "scope": "global", "property_id": None, "category": "experience",
         "name": "Candlelight Dinner", "price": 3500.0, "price_basis": "per_stay",
         "eligibility": None, "segment_affinity": ["couple", "honeymoon", "anniversary"]},
    ]
    for p in properties:
        if p["type"] in ("resort", "villa") and "spa" in p["amenities"]:
            addons.append({
                "id": f"addon-spa-{p['id']}", "scope": "property", "property_id": p["id"],
                "category": "experience", "name": "In-house Spa Session", "price": 2800.0,
                "price_basis": "per_person", "eligibility": None,
                "segment_affinity": ["couple", "leisure"],
            })
    return addons


def main() -> None:
    rng = random.Random(SEED)
    properties: list[dict] = []
    rates: list[dict] = []
    inventory: list[dict] = []
    policies_by_prop: dict[str, list[dict]] = {}

    edge_props, edge_rooms, edge_rates, edge_inv, edge_policies = edge_case_properties(random.Random(SEED))
    rooms_by_prop: dict[str, list[dict]] = {}
    for p in edge_props:
        properties.append(p)
        rooms_by_prop[p["id"]] = [r for r in edge_rooms if r["property_id"] == p["id"]]
    rates += edge_rates
    inventory += edge_inv
    for pol in edge_policies:
        policies_by_prop.setdefault(pol["property_id"], []).append(pol)

    city_counts = {"Goa": 2, "Jaipur": 2, "Udaipur": 2, "Rishikesh": 2, "Manali": 2, "Coorg": 2, "Lonavala": 2, "Alibaug": 2}
    seq = 1
    for city, count in city_counts.items():
        for _ in range(count):
            prop, rooms, r, inv, policies = generate_property(rng, city, seq)
            seq += 1
            properties.append(prop)
            rooms_by_prop[prop["id"]] = rooms
            rates += r
            inventory += inv
            for pol in policies:
                policies_by_prop.setdefault(pol["property_id"], []).append(pol)

    # Embed room_types and policies into each property record (properties.json is the browsable source of truth).
    for p in properties:
        p["room_types"] = rooms_by_prop.get(p["id"], [])
        p["policies"] = policies_by_prop.get(p["id"], [])

    addons = generate_addons(properties)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "properties.json").write_text(json.dumps({
        "demo_today": DEMO_TODAY.isoformat(),
        "window_days": WINDOW_DAYS,
        "tax_rule": TAX_RULE,
        "properties": properties,
    }, indent=2), encoding="utf-8")
    (DATA_DIR / "rates.json").write_text(json.dumps(rates, indent=2), encoding="utf-8")
    (DATA_DIR / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (DATA_DIR / "addons.json").write_text(json.dumps(addons, indent=2), encoding="utf-8")

    n_rooms = sum(len(p["room_types"]) for p in properties)
    print(f"Wrote {len(properties)} properties ({n_rooms} room types), "
          f"{len(rates)} rate rows, {len(inventory)} inventory rows, {len(addons)} add-ons.")


if __name__ == "__main__":
    main()
