from pathlib import Path
from unittest.mock import patch

import pytest

from app.data.indexes import CityIndex
from app.data.loader import build_database
from app.data.repo import Repo
from app.domain.state import ConversationState, OptionRef
from app.domain.trace import NextAction, NextActionType
from app.pipeline.act import TurnServices, run_action
from app.pipeline.policy import TurnContext
from app.store.holds import HoldStore
from app.tools.registry import build_default_registry
from app.domain.trace import UserAct

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Repo:
    db_path = tmp_path_factory.mktemp("db") / "mira_test.db"
    conn = build_database(DATA_DIR, db_path)
    return Repo(conn)


def test_registry_has_all_six_tools(repo: Repo):
    registry = build_default_registry(repo, CityIndex(repo), HoldStore(), repo.get_demo_today())
    assert registry.names() == sorted([
        "search_properties", "check_availability", "get_room_details",
        "get_property_policies", "calculate_quote", "create_booking_hold",
    ])


def test_registry_exports_json_schema(repo: Repo):
    registry = build_default_registry(repo, CityIndex(repo), HoldStore(), repo.get_demo_today())
    schemas = registry.export_schemas()
    assert "properties" in schemas["search_properties"]["args_schema"]
    assert schemas["calculate_quote"]["result_schema"] is not None


def test_registry_validate_args_rejects_bad_input(repo: Repo):
    registry = build_default_registry(repo, CityIndex(repo), HoldStore(), repo.get_demo_today())
    spec = registry.get("check_availability")
    with pytest.raises(Exception):
        spec.validate_args({"room_type_id": "r1"})  # missing required check_in/check_out


def test_registry_call_executes_tool(repo: Repo):
    registry = build_default_registry(repo, CityIndex(repo), HoldStore(), repo.get_demo_today())
    prop = repo.all_properties()[0]
    result = registry.get("get_property_policies").call({"property_id": prop.id, "keys": []})
    assert result.property_id == prop.id


def test_tool_error_surfaces_as_failed_toolcall_not_a_crash(repo: Repo):
    state = ConversationState(conversation_id="c1")
    state.intent.destination.value = None  # will be set below via direct mutation for search args
    from app.domain.intent import Destination, Party, Slot, StayWindow
    state.intent.destination = Slot(value=Destination(city="Goa"))
    state.intent.stay = Slot(value=StayWindow(check_in="2026-09-04", check_out="2026-09-06", nights=2))
    state.intent.party = Slot(value=Party(adults=2))

    ctx = TurnContext(user_act=UserAct.NEW_REQUEST)
    services = TurnServices(repo=repo, city_index=CityIndex(repo), hold_store=HoldStore(), today=repo.get_demo_today())

    with patch("app.tools.registry.search_properties", side_effect=RuntimeError("catalogue exploded")):
        tc = run_action(NextAction(type=NextActionType.SEARCH), state, ctx, services)

    assert tc is not None
    assert tc.ok is False
    assert "catalogue exploded" in tc.error
