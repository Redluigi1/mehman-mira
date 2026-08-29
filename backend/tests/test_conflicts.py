from datetime import date, timedelta
from pathlib import Path

import pytest

from app.data.loader import build_database
from app.data.repo import Repo
from app.domain.intent import Budget, BudgetBasis, Party, PolicyNeeds, Slot, StayWindow
from app.domain.state import ConflictKind, ConversationState, OptionRef
from app.pipeline.conflicts import sync_conflicts

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Repo:
    db_path = tmp_path_factory.mktemp("db") / "mira_test.db"
    conn = build_database(DATA_DIR, db_path)
    return Repo(conn)


def _option(**overrides) -> OptionRef:
    base = dict(option_id="p:r", property_id="p", room_type_id="r", ordinal=1,
                property_name="P", room_type_name="R", city="Goa", star_tier=4,
                rooms_needed=1, nights=2, price_per_night=5000.0, estimated_total=10000.0)
    base.update(overrides)
    return OptionRef(**base)


def _state_with_dates(repo: Repo, **stay_overrides) -> tuple[ConversationState, date]:
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    check_in = stay_overrides.pop("check_in", today)
    check_out = stay_overrides.pop("check_out", today + timedelta(days=2))
    state.intent.stay = Slot(value=StayWindow(
        check_in=check_in.isoformat() if hasattr(check_in, "isoformat") else check_in,
        check_out=check_out.isoformat() if hasattr(check_out, "isoformat") else check_out,
        nights=2,
    ))
    return state, today


# -- hard conflicts: pure functions of intent, reappear every turn -----------

def test_past_check_in_is_a_conflict(repo: Repo):
    state, today = _state_with_dates(repo, check_in=today_minus(repo, 3), check_out=today_minus(repo, 1))
    sync_conflicts(state, repo, today)
    kinds = {c.kind for c in state.conflicts}
    assert ConflictKind.PAST_DATE in kinds


def today_minus(repo: Repo, days: int):
    return repo.get_demo_today() - timedelta(days=days)


def test_checkout_before_checkin_is_a_contradiction(repo: Repo):
    today = repo.get_demo_today()
    state, _ = _state_with_dates(repo, check_in=today + timedelta(days=5), check_out=today + timedelta(days=3))
    sync_conflicts(state, repo, today)
    kinds = {c.kind for c in state.conflicts}
    assert ConflictKind.CONTRADICTION in kinds


def test_negative_party_is_a_contradiction(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.intent.party = Slot(value=Party(adults=-1))
    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.CONTRADICTION for c in state.conflicts)


def test_hard_conflict_never_auto_resolves(repo: Repo):
    today = repo.get_demo_today()
    state, _ = _state_with_dates(repo, check_in=today_minus(repo, 3), check_out=today_minus(repo, 1))
    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.PAST_DATE and not c.resolved for c in state.conflicts)
    sync_conflicts(state, repo, today)  # unchanged state, called again
    assert any(c.kind == ConflictKind.PAST_DATE and not c.resolved for c in state.conflicts)


def test_no_conflicts_when_dates_are_clean(repo: Repo):
    today = repo.get_demo_today()
    state, _ = _state_with_dates(repo)
    sync_conflicts(state, repo, today)
    assert state.conflicts == []


# -- soft conflicts: tied to the focused option, surfaced once ---------------

def test_capacity_conflict_when_party_outgrows_focused_room(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.focused_option = _option(
        option_id="goa-edge-cap2:goa-edge-cap2-rt1", property_id="goa-edge-cap2",
        room_type_id="goa-edge-cap2-rt1", property_name="Cove Corner Guesthouse", room_type_name="Cozy Double",
        rooms_needed=1, nights=2, price_per_night=3200.0, estimated_total=6400.0,
    )
    state.intent.party = Slot(value=Party(adults=5))
    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.CAPACITY for c in state.conflicts)


def test_no_capacity_conflict_when_party_fits(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.focused_option = _option(
        option_id="goa-edge-cap2:goa-edge-cap2-rt1", property_id="goa-edge-cap2",
        room_type_id="goa-edge-cap2-rt1", property_name="Cove Corner Guesthouse", room_type_name="Cozy Double",
        rooms_needed=1, nights=2, price_per_night=3200.0, estimated_total=6400.0,
    )
    state.intent.party = Slot(value=Party(adults=2))
    sync_conflicts(state, repo, today)
    assert not any(c.kind == ConflictKind.CAPACITY for c in state.conflicts)


def test_policy_conflict_when_guest_needs_smoking_at_nosmoking_property(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.focused_option = _option(
        option_id="goa-edge-nosmoking:goa-edge-nosmoking-rt1", property_id="goa-edge-nosmoking",
        room_type_id="goa-edge-nosmoking-rt1", property_name="Whitesands Boutique", room_type_name="Deluxe Room",
    )
    state.intent.policy_needs = Slot(value=PolicyNeeds(smoking=True))
    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.POLICY for c in state.conflicts)


def test_min_stay_conflict_when_nights_below_property_minimum(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.intent.stay = Slot(value=StayWindow(
        check_in=today.isoformat(), check_out=(today + timedelta(days=2)).isoformat(), nights=2,
    ))
    state.focused_option = _option(
        option_id="goa-edge-minstay3:goa-edge-minstay3-rt1", property_id="goa-edge-minstay3",
        room_type_id="goa-edge-minstay3-rt1", property_name="Riverside Manor", room_type_name="Superior Room",
        nights=2,
    )
    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.MIN_STAY for c in state.conflicts)


def test_budget_conflict_when_hard_ceiling_below_focused_option_total(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.intent.budget = Slot(value=Budget(amount=5000, basis=BudgetBasis.PER_NIGHT, hard=True))
    state.focused_option = _option(
        option_id="goa-edge-villa8:goa-edge-villa8-rt1", property_id="goa-edge-villa8",
        room_type_id="goa-edge-villa8-rt1", property_name="Grand Dunes Villa", room_type_name="Entire Villa (4BHK)",
        nights=2, price_per_night=18000.0, estimated_total=36000.0,
    )
    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.BUDGET for c in state.conflicts)


def test_soft_conflict_is_surfaced_once_then_treated_as_acknowledged(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.focused_option = _option(
        option_id="goa-edge-cap2:goa-edge-cap2-rt1", property_id="goa-edge-cap2",
        room_type_id="goa-edge-cap2-rt1", property_name="Cove Corner Guesthouse", room_type_name="Cozy Double",
    )
    state.intent.party = Slot(value=Party(adults=5))

    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.CAPACITY and not c.resolved for c in state.conflicts)

    sync_conflicts(state, repo, today)  # same turn's condition, called again unchanged
    assert all(c.resolved for c in state.conflicts if c.kind == ConflictKind.CAPACITY)


def test_soft_conflict_clears_when_focused_option_changes(repo: Repo):
    today = repo.get_demo_today()
    state = ConversationState(conversation_id="c1")
    state.focused_option = _option(
        option_id="goa-edge-cap2:goa-edge-cap2-rt1", property_id="goa-edge-cap2",
        room_type_id="goa-edge-cap2-rt1", property_name="Cove Corner Guesthouse", room_type_name="Cozy Double",
    )
    state.intent.party = Slot(value=Party(adults=5))
    sync_conflicts(state, repo, today)
    assert any(c.kind == ConflictKind.CAPACITY for c in state.conflicts)

    state.focused_option = _option(
        option_id="goa-edge-villa8:goa-edge-villa8-rt1", property_id="goa-edge-villa8",
        room_type_id="goa-edge-villa8-rt1", property_name="Grand Dunes Villa", room_type_name="Entire Villa (4BHK)",
    )
    sync_conflicts(state, repo, today)
    assert not any(c.kind == ConflictKind.CAPACITY for c in state.conflicts)
