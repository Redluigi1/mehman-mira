from datetime import date, timedelta
from pathlib import Path

import pytest

from app.data.indexes import AvailabilityIndex
from app.data.loader import build_database
from app.data.repo import Repo

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

EDGE_CASE_IDS = [
    "goa-edge-dateshift",
    "goa-edge-unknown",
    "goa-edge-nosmoking",
    "goa-edge-cap2",
    "goa-edge-villa8",
    "goa-edge-pricecliff",
    "goa-edge-minstay3",
    "goa-edge-fullybooked",
]


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Repo:
    db_path = tmp_path_factory.mktemp("db") / "mira_test.db"
    conn = build_database(DATA_DIR, db_path)
    return Repo(conn)


def test_property_and_room_counts(repo: Repo):
    properties = repo.all_properties()
    assert len(properties) == 24
    total_rooms = sum(len(repo.get_room_types(p.id)) for p in properties)
    assert 60 <= total_rooms <= 80


def test_eight_cities(repo: Repo):
    assert len(repo.all_cities()) == 8


def test_goa_is_dense(repo: Repo):
    goa = repo.list_properties_by_city("Goa")
    assert len(goa) >= 10


def test_every_planted_edge_case_exists(repo: Repo):
    for pid in EDGE_CASE_IDS:
        prop = repo.get_property(pid)
        assert prop is not None, f"missing edge-case property {pid}"
        rooms = repo.get_room_types(pid)
        assert len(rooms) >= 1


def test_date_shift_edge_case(repo: Repo):
    demo_today = repo.get_demo_today()
    room = repo.get_room_types("goa-edge-dateshift")[0]
    idx = AvailabilityIndex(repo, [room.id], demo_today, demo_today + timedelta(days=21))
    assert idx.min_units_available(room.id, demo_today, demo_today + timedelta(days=2)) == 0
    assert idx.min_units_available(room.id, demo_today + timedelta(days=3), demo_today + timedelta(days=5)) > 0


def test_unknown_info_edge_case(repo: Repo):
    pv = repo.get_policy("goa-edge-unknown", "pool_heated")
    assert pv.status == "unknown"


def test_policy_conflict_edge_case(repo: Repo):
    pv = repo.get_policy("goa-edge-nosmoking", "smoking")
    assert pv.status == "known" and pv.value is False


def test_capacity_conflict_edge_case(repo: Repo):
    room = repo.get_room_types("goa-edge-cap2")[0]
    assert room.max_occupancy == 2


def test_capacity_split_edge_case(repo: Repo):
    room = repo.get_room_types("goa-edge-villa8")[0]
    assert room.max_occupancy == 8


def test_price_cliff_edge_case(repo: Repo):
    demo_today = repo.get_demo_today()
    room = repo.get_room_types("goa-edge-pricecliff")[0]
    early = repo.get_rates(room.id, demo_today, demo_today + timedelta(days=1))[0]
    late = repo.get_rates(room.id, demo_today + timedelta(days=15), demo_today + timedelta(days=16))[0]
    assert late.price > early.price * 1.5


def test_min_stay_edge_case(repo: Repo):
    demo_today = repo.get_demo_today()
    room = repo.get_room_types("goa-edge-minstay3")[0]
    rate = repo.get_rates(room.id, demo_today, demo_today + timedelta(days=1))[0]
    assert rate.min_stay == 3


def test_fully_booked_edge_case(repo: Repo):
    demo_today = repo.get_demo_today()
    room = repo.get_room_types("goa-edge-fullybooked")[0]
    idx = AvailabilityIndex(repo, [room.id], demo_today, demo_today + timedelta(days=21))
    assert idx.min_units_available(room.id, demo_today, demo_today + timedelta(days=21)) == 0


def test_addons_loaded(repo: Repo):
    addons = repo.get_addons()
    assert len(addons) >= 3


def test_tax_rule_loaded(repo: Repo):
    tax = repo.get_tax_rule()
    assert tax.gst_percent_for(5000) == 12.0
    assert tax.gst_percent_for(10000) == 18.0
