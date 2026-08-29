"""suggest_addons — eligibility and ranking (Bonus 1, plan §7)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.data.loader import build_database
from app.data.repo import Repo
from app.domain.state import ConversationState, OptionRef, Quote, QuoteLineItem
from app.domain.trace import NextActionType, UserAct
from app.pipeline.addon_selection import resolve_addon_response
from app.pipeline.policy import TurnContext, decide
from app.tools.addons import suggest_addons
from app.tools.types import SuggestAddonsArgs, SuggestedAddon

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Repo:
    db_path = tmp_path_factory.mktemp("db") / "mira_test.db"
    conn = build_database(DATA_DIR, db_path)
    return Repo(conn)


def test_airport_pickup_only_eligible_with_shuttle_amenity(repo: Repo):
    with_shuttle = suggest_addons(repo, SuggestAddonsArgs(property_id="alibaug-gen-16"))
    without_shuttle = suggest_addons(repo, SuggestAddonsArgs(property_id="alibaug-gen-15"))
    assert any(s.id == "addon-airport-pickup" for s in with_shuttle.suggestions)
    assert not any(s.id == "addon-airport-pickup" for s in without_shuttle.suggestions)


def test_guaranteed_early_checkin_ineligible_once_already_free(repo: Repo):
    # coorg-gen-11's early_checkin policy is known True — already free and
    # guaranteed, so paying to "guarantee" it again would be a bad upsell.
    result = suggest_addons(repo, SuggestAddonsArgs(property_id="coorg-gen-11"))
    assert not any(s.id == "addon-early-checkin" for s in result.suggestions)


def test_at_most_two_suggestions_with_reasons(repo: Repo):
    result = suggest_addons(repo, SuggestAddonsArgs(
        property_id="alibaug-gen-16", party_type="couple", occasion="anniversary",
    ))
    assert 0 < len(result.suggestions) <= 2
    assert all(s.reason for s in result.suggestions)


def test_explicit_occasion_ranks_above_unrelated_addon(repo: Repo):
    result = suggest_addons(repo, SuggestAddonsArgs(property_id="alibaug-gen-16", occasion="anniversary"))
    assert result.suggestions[0].id == "addon-candlelight-dinner"
    assert "anniversary" in result.suggestions[0].reason


# --- accepted add-ons actually reach the quote (regression: they used to be discarded) ---

_PICKUP = SuggestedAddon(id="addon-airport-pickup", name="Airport Pickup", price=1500, price_basis="per_stay", reason="shuttle")
_BREAKFAST = SuggestedAddon(id="addon-breakfast", name="Daily Breakfast", price=450, price_basis="per_person", reason="popular")


def test_resolve_addon_response_reads_per_clause_accept_and_decline():
    accepted = resolve_addon_response(
        "Let's add the airport pickup, skip breakfast.", [_PICKUP, _BREAKFAST], previously_accepted=[],
    )
    assert accepted == ["addon-airport-pickup"]


def test_resolve_addon_response_keeps_prior_accept_when_unmentioned():
    accepted = resolve_addon_response("sounds good", [_PICKUP, _BREAKFAST], previously_accepted=["addon-airport-pickup"])
    assert accepted == ["addon-airport-pickup"]


def test_resolve_addon_response_can_retract_a_prior_accept():
    accepted = resolve_addon_response(
        "actually skip the airport pickup after all", [_PICKUP, _BREAKFAST], previously_accepted=["addon-airport-pickup"],
    )
    assert accepted == []


def test_decide_rebuilds_quote_when_accepted_addons_diverge_from_baked_in_quote():
    option = OptionRef(
        option_id="a", property_id="prop-a", room_type_id="room-a", ordinal=1, property_name="Prop", room_type_name="Deluxe",
        city="Goa", star_tier=4, rooms_needed=1, nights=2, price_per_night=4000, estimated_total=8000,
    )
    state = ConversationState(conversation_id="c-addon")
    state.shortlist = [option]
    state.focused_option = option
    state.quote = Quote(option_id="a", nights=2, room_subtotal=8000, line_items=[QuoteLineItem(label="Room", amount=8000)],
                         taxes=0, fixed_fees=0, total=8000)
    state.quote_addon_ids = []
    state.upsell_offered_for_quote = "a"  # already offered, guest is now answering
    state.accepted_addon_ids = ["addon-airport-pickup"]  # resolved from the guest's reply this turn

    ctx = TurnContext(user_act=UserAct.ANSWER, eligible_addons=[_PICKUP])
    action = decide(state, ctx)
    assert action.type == NextActionType.QUOTE  # rebuild owed before any hold, not silently dropped
