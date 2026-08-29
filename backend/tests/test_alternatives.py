from datetime import timedelta
from pathlib import Path

import pytest

from app.data.indexes import CityIndex
from app.data.loader import build_database
from app.data.repo import Repo
from app.domain.state import RelaxationKind
from app.tools.alternatives import find_alternatives
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


def test_impossible_budget_falls_back_to_ceiling_dropped(repo: Repo, city_index: CityIndex):
    """EC7 — a budget far below anything in the catalogue (more than the 20%
    near-miss threshold search_properties itself tolerates) should still come
    back with something: the honest floor, not a bare 'nothing found'.
    """
    today = repo.get_demo_today()
    args = SearchArgs(
        city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(),
        adults=2, budget_amount=100.0, budget_basis="per_night",
    )
    result = find_alternatives(repo, city_index, args)
    assert result.exact or result.near_miss
    assert result.strategy == "budget_ceiling_dropped"
    all_hits = result.exact + result.near_miss
    assert any(any(r.kind == RelaxationKind.OVER_BUDGET for r in h.relaxations) for h in all_hits) or result.exact


def test_amenities_dropped_when_no_property_has_them(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(
        city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(),
        adults=2, amenities_required=["a_totally_fictional_amenity"],
    )
    result = find_alternatives(repo, city_index, args)
    assert result.exact or result.near_miss
    assert result.strategy == "amenities_dropped"


def test_unknown_city_reaches_the_honest_floor_and_finds_nothing(repo: Repo, city_index: CityIndex):
    today = repo.get_demo_today()
    args = SearchArgs(
        city="Atlantis", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=2,
    )
    result = find_alternatives(repo, city_index, args)
    assert result.exact == [] and result.near_miss == []
    assert result.strategy == "none"


def test_plain_search_leaves_strategy_empty(repo: Repo, city_index: CityIndex):
    from app.tools.search import search_properties

    today = repo.get_demo_today()
    args = SearchArgs(city="Goa", check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), adults=2)
    result = search_properties(repo, city_index, args)
    assert result.strategy == ""
