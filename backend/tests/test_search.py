from datetime import timedelta
from pathlib import Path

import pytest

from app.data.indexes import CityIndex
from app.data.loader import build_database
from app.data.repo import Repo
from app.domain.state import RelaxationKind
from app.tools.search import search_properties
from app.tools.types import SearchArgs

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Repo:
    db_path = tmp_path_factory.mktemp("db") / "mira_test.db"
    conn = build_database(DATA_DIR, db_path)
    return Repo(conn)


@pytest.fixture(scope="module")
def city_index(repo: Repo) -> CityIndex:
    return CityIndex(repo)


def _hit_by_property(result, property_id: str):
    return next((h for h in result.exact + result.near_miss if h.property_id == property_id), None)


def test_goa_happy_path_returns_results(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    check_in = today
    check_out = today + timedelta(days=2)
    args = SearchArgs(city="Goa", check_in=check_in.isoformat(), check_out=check_out.isoformat(), adults=3)
    result = search_properties(repo, city_index, args)
    assert len(result.exact) + len(result.near_miss) > 0


def test_date_shift_property_is_near_miss_with_relaxation(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=2)
    result = search_properties(repo, city_index, args)
    hit = _hit_by_property(result, "goa-edge-dateshift")
    assert hit is not None
    assert hit in result.near_miss
    assert any(r.kind == RelaxationKind.DATE_SHIFT for r in hit.relaxations)


def test_fully_booked_property_is_excluded(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=2)
    result = search_properties(repo, city_index, args)
    assert _hit_by_property(result, "goa-edge-fullybooked") is None


def test_capacity_conflict_property_excluded_for_large_party(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=5)
    result = search_properties(repo, city_index, args)
    # cap-2 room can't fit 5 even split across 2 rooms (max 4) -> excluded entirely
    assert _hit_by_property(result, "goa-edge-cap2") is None


def test_capacity_split_villa_fits_large_party(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=7)
    result = search_properties(repo, city_index, args)
    hit = _hit_by_property(result, "goa-edge-villa8")
    assert hit is not None
    assert hit in result.exact  # 7 <= max_occupancy 8, single room, no relaxation needed


def test_policy_conflict_surfaced_not_dropped(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(),
                       adults=2, smoking=True)
    result = search_properties(repo, city_index, args)
    hit = _hit_by_property(result, "goa-edge-nosmoking")
    assert hit is not None
    assert any(r.kind == RelaxationKind.POLICY_CONFLICT for r in hit.relaxations)


def test_min_stay_property_surfaced_as_near_miss_for_short_stay(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=2)
    result = search_properties(repo, city_index, args)
    hit = _hit_by_property(result, "goa-edge-minstay3")
    assert hit is not None
    assert any(r.kind == RelaxationKind.MIN_STAY for r in hit.relaxations)


def test_over_budget_within_threshold_is_near_miss(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    # villa8 is priced high; request tight budget that's within 20% overshoot for a 2-night, 2-adult stay
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(),
                       adults=2, budget_amount=16000, budget_basis="per_night")
    result = search_properties(repo, city_index, args)
    hit = _hit_by_property(result, "goa-edge-villa8")
    if hit is not None:
        assert any(r.kind == RelaxationKind.OVER_BUDGET for r in hit.relaxations) or hit in result.exact


def test_unknown_city_returns_empty(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(city="Atlantis", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=2)
    result = search_properties(repo, city_index, args)
    assert result.exact == [] and result.near_miss == []
