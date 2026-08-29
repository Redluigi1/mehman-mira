"""calculate_quote unit tests against hand-computed fixtures (Decision 004).

A minimal, fully controlled dataset (flat $5000/night rate, no weekend
premium) is loaded so every expected total below was computed by hand,
independent of the seeded generator.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from app.data.loader import build_database
from app.data.repo import Repo
from app.tools.pricing import calculate_quote
from app.tools.types import QuoteArgs

TODAY = date(2026, 1, 1)


def _write_minimal_dataset(tmp_path: Path, *, nightly_rate: float = 5000.0, min_stay: int = 1) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    dates = [date(2026, 1, d).isoformat() for d in range(1, 15)]
    properties = {
        "demo_today": TODAY.isoformat(),
        "window_days": 14,
        "tax_rule": {
            "slabs": [{"max_per_night_rate": 7500.0, "gst_percent": 12.0}, {"max_per_night_rate": None, "gst_percent": 18.0}],
            "fixed_fee_per_stay": 250.0,
        },
        "properties": [{
            "id": "p1", "name": "Test Property", "city": "TestCity", "area": None, "geo": None,
            "type": "hotel", "star_tier": 4, "description": "d", "amenities": [], "images": [],
            "check_in_time": "14:00", "check_out_time": "11:00",
            "room_types": [{
                "id": "r1", "property_id": "p1", "name": "Room", "base_occupancy": 2, "max_occupancy": 3,
                "max_adults": 3, "max_children": 1, "extra_bed_allowed": True, "extra_bed_price": 1000.0,
                "bed_config": "king", "size_sqft": 300, "view": "none", "amenities": [], "units_total": 5,
            }],
            "policies": [],
        }],
    }
    rates = [{"room_type_id": "r1", "date": d, "price": nightly_rate, "min_stay": min_stay, "closed_to_arrival": False} for d in dates]
    inventory = [{"room_type_id": "r1", "date": d, "units_available": 5} for d in dates]
    addons = [{"id": "a1", "scope": "global", "property_id": None, "category": "food", "name": "Breakfast",
               "price": 1500.0, "price_basis": "per_stay", "eligibility": None, "segment_affinity": []}]

    (data_dir / "properties.json").write_text(json.dumps(properties))
    (data_dir / "rates.json").write_text(json.dumps(rates))
    (data_dir / "inventory.json").write_text(json.dumps(inventory))
    (data_dir / "addons.json").write_text(json.dumps(addons))
    return data_dir


@pytest.fixture
def repo(tmp_path) -> Repo:
    data_dir = _write_minimal_dataset(tmp_path)
    conn = build_database(data_dir, tmp_path / "db" / "t.db")
    return Repo(conn)


def _args(**overrides) -> QuoteArgs:
    base = dict(option_id="p1:r1", property_id="p1", room_type_id="r1",
                check_in="2026-01-01", check_out="2026-01-03", rooms_needed=1)
    base.update(overrides)
    return QuoteArgs(**base)


def test_three_nights_no_discount(repo: Repo):
    q = calculate_quote(repo, _args(check_out="2026-01-04"), TODAY)
    assert q.room_subtotal == 15000.0
    assert q.taxes == pytest.approx(1800.0)
    assert q.fixed_fees == 250.0
    assert q.total == pytest.approx(17050.0)


def test_four_nights_los_discount(repo: Repo):
    q = calculate_quote(repo, _args(check_out="2026-01-05"), TODAY)
    assert q.room_subtotal == 20000.0
    assert q.total == pytest.approx(21978.0)


def test_seven_nights_los_discount(repo: Repo):
    q = calculate_quote(repo, _args(check_out="2026-01-08"), TODAY)
    assert q.room_subtotal == 35000.0
    assert q.total == pytest.approx(37490.0)


def test_extra_bed_charge(repo: Repo):
    q = calculate_quote(repo, _args(extra_beds=1), TODAY)
    assert q.room_subtotal == 12000.0
    assert q.total == pytest.approx(13690.0)


def test_addon_per_stay(repo: Repo):
    q = calculate_quote(repo, _args(add_on_ids=["a1"]), TODAY)
    assert q.total == pytest.approx(12950.0)


def test_early_bird_discount_isolated(tmp_path):
    data_dir = _write_minimal_dataset(tmp_path)
    # extend rates to cover a date 40+ days out
    rates = json.loads((data_dir / "rates.json").read_text())
    rates += [{"room_type_id": "r1", "date": date(2026, 2, d).isoformat(), "price": 5000.0, "min_stay": 1, "closed_to_arrival": False} for d in range(9, 13)]
    (data_dir / "rates.json").write_text(json.dumps(rates))
    inv = json.loads((data_dir / "inventory.json").read_text())
    inv += [{"room_type_id": "r1", "date": date(2026, 2, d).isoformat(), "units_available": 5} for d in range(9, 13)]
    (data_dir / "inventory.json").write_text(json.dumps(inv))
    conn = build_database(data_dir, tmp_path / "db2" / "t.db")
    repo = Repo(conn)
    q = calculate_quote(repo, _args(check_in="2026-02-10", check_out="2026-02-12"), TODAY)
    assert q.total == pytest.approx(10890.0)


def test_seasonal_tax_slab_jump(tmp_path):
    data_dir = _write_minimal_dataset(tmp_path, nightly_rate=8000.0)
    conn = build_database(data_dir, tmp_path / "db3" / "t.db")
    repo = Repo(conn)
    q = calculate_quote(repo, _args(check_out="2026-01-03"), TODAY)
    assert q.room_subtotal == 16000.0
    assert q.taxes == pytest.approx(2880.0)
    assert q.total == pytest.approx(19130.0)


def test_min_stay_data_present_but_not_enforced_here(tmp_path):
    # calculate_quote prices whatever range is requested; min-stay enforcement
    # is a search/policy concern (RelaxationKind.MIN_STAY), not a pricing one.
    data_dir = _write_minimal_dataset(tmp_path, min_stay=3)
    conn = build_database(data_dir, tmp_path / "db4" / "t.db")
    repo = Repo(conn)
    q = calculate_quote(repo, _args(check_out="2026-01-03"), TODAY)
    assert q is not None
    assert q.nights == 2
