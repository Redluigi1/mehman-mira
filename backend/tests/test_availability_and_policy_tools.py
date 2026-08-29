from datetime import timedelta
from pathlib import Path

import pytest

from app.data.loader import build_database
from app.data.repo import Repo
from app.tools.availability import check_availability, get_room_details
from app.tools.policy_tool import get_property_policies
from app.tools.types import AvailabilityArgs, PropertyPoliciesArgs, RoomDetailsArgs

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Repo:
    db_path = tmp_path_factory.mktemp("db") / "mira_test.db"
    conn = build_database(DATA_DIR, db_path)
    return Repo(conn)


def test_check_availability_fully_booked_property(repo: Repo):
    today = repo.get_demo_today()
    room = repo.get_room_types("goa-edge-fullybooked")[0]
    result = check_availability(repo, AvailabilityArgs(
        room_type_id=room.id, check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(),
    ))
    assert result.units_available == 0
    assert result.is_available is False


def test_check_availability_min_stay_flag(repo: Repo):
    today = repo.get_demo_today()
    room = repo.get_room_types("goa-edge-minstay3")[0]
    result = check_availability(repo, AvailabilityArgs(
        room_type_id=room.id, check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(),
    ))
    assert result.min_stay == 3
    assert result.meets_min_stay is False


def test_get_room_details_villa(repo: Repo):
    room = repo.get_room_types("goa-edge-villa8")[0]
    details = get_room_details(repo, RoomDetailsArgs(room_type_id=room.id))
    assert details is not None
    assert details.max_occupancy == 8
    assert details.property_name == "Grand Dunes Villa"


def test_get_room_details_missing_returns_none(repo: Repo):
    assert get_room_details(repo, RoomDetailsArgs(room_type_id="does-not-exist")) is None


def test_get_property_policies_unknown_pool_heated(repo: Repo):
    result = get_property_policies(repo, PropertyPoliciesArgs(property_id="goa-edge-unknown"))
    assert result is not None
    pool = next(p for p in result.policies if p.key == "pool_heated")
    assert pool.status == "unknown"
    assert pool.value is None


def test_get_property_policies_strict_no_smoking(repo: Repo):
    result = get_property_policies(repo, PropertyPoliciesArgs(property_id="goa-edge-nosmoking", keys=["smoking"]))
    assert result is not None
    assert result.policies[0].status == "known"
    assert result.policies[0].value is False


def test_get_property_policies_missing_property(repo: Repo):
    assert get_property_policies(repo, PropertyPoliciesArgs(property_id="nope")) is None
