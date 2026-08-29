"""Conversation-recovery phrases (Bonus 2, plan §7): the five phrasings the
brief calls out by name. Each is driven through the same deterministic
pipeline stages the other Phase 3 tests use — no live LLM involved, since
what's being proven is that once `referent_mentions`/`objection`/`user_act`
are extracted, the deterministic code recovers sensibly.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.state import (
    ConversationState, OptionRef, Quote, QuoteLineItem, Rejection, RejectionReason,
)
from app.domain.trace import NextActionType, UserAct
from app.pipeline.act import _apply_search_result_to_state
from app.pipeline.extract import Objection
from app.pipeline.policy import TurnContext, decide
from app.pipeline.referents import resolve_selection
from app.tools.types import SearchHit, SearchResult, SuggestedAddon


def _option(option_id: str, ordinal: int, price: float) -> OptionRef:
    return OptionRef(
        option_id=option_id, property_id=f"prop-{option_id}", room_type_id=f"room-{option_id}", ordinal=ordinal,
        property_name=f"Property {ordinal}", room_type_name="Deluxe", city="Goa", star_tier=4,
        rooms_needed=1, nights=2, price_per_night=price, estimated_total=price * 2,
    )


def _state_with_shortlist(*options: OptionRef) -> ConversationState:
    state = ConversationState(conversation_id="c-recovery")
    state.shortlist = list(options)
    state.referents = state.referents.replace(list(options))
    return state


# 1. "yes" — accepts a quote; upsell offered once, then holds ----------------

def test_recovery_yes_holds_when_no_addons_eligible():
    state = _state_with_shortlist(_option("a", 1, 4000))
    state.focused_option = state.shortlist[0]
    state.quote = Quote(option_id="a", nights=2, room_subtotal=8000, line_items=[QuoteLineItem(label="Room", amount=8000)],
                         taxes=0, fixed_fees=0, total=8000)
    ctx = TurnContext(user_act=UserAct.ANSWER)  # no eligible_addons
    action = decide(state, ctx)
    assert action.type == NextActionType.HOLD


def test_recovery_yes_upsells_once_then_holds():
    state = _state_with_shortlist(_option("a", 1, 4000))
    state.focused_option = state.shortlist[0]
    state.quote = Quote(option_id="a", nights=2, room_subtotal=8000, line_items=[QuoteLineItem(label="Room", amount=8000)],
                         taxes=0, fixed_fees=0, total=8000)
    addon = SuggestedAddon(id="addon-breakfast", name="Daily Breakfast", price=450, price_basis="per_person", reason="popular here")

    ctx = TurnContext(user_act=UserAct.ANSWER, eligible_addons=[addon])
    first = decide(state, ctx)
    assert first.type == NextActionType.UPSELL  # offered before the hold, not instead of it

    state.upsell_offered_for_quote = state.quote.option_id  # what run_action's _do_upsell would set
    second = decide(state, ctx)
    assert second.type == NextActionType.HOLD  # not re-offered on the guest's next turn


# 2. "too expensive" — objection with no search yet this turn -> refine ------

def test_recovery_too_expensive_refines_search():
    state = _state_with_shortlist(_option("a", 1, 9000))
    state.focused_option = state.shortlist[0]
    ctx = TurnContext(user_act=UserAct.OBJECTION, objection=Objection(kind=RejectionReason.PRICE, detail="too expensive"))
    action = decide(state, ctx)
    assert action.type == NextActionType.REFINE_SEARCH


# 3. "whichever is better" — defers to the shortlist's own ranking -----------

def test_recovery_whichever_is_better_picks_top_ranked():
    state = _state_with_shortlist(_option("a", 1, 4000), _option("b", 2, 3000))
    selected = resolve_selection(state, ["whichever is better for us"], repo=_NullRepo())
    assert selected is not None and selected.option_id == "a"  # ordinal 1 = best match, not cheapest


# 4. "what about the other one?" — switches to the only other option --------

def test_recovery_other_one_switches_between_exactly_two():
    state = _state_with_shortlist(_option("a", 1, 4000), _option("b", 2, 5000))
    state.focused_option = state.shortlist[0]
    selected = resolve_selection(state, ["what about the other one?"], repo=_NullRepo())
    assert selected is not None and selected.option_id == "b"


def test_recovery_other_one_ambiguous_with_three_options_falls_through():
    state = _state_with_shortlist(_option("a", 1, 4000), _option("b", 2, 5000), _option("c", 3, 6000))
    state.focused_option = state.shortlist[0]
    selected = resolve_selection(state, ["what about the other one?"], repo=_NullRepo())
    assert selected is None


# 5. "any cheaper option?" — re-presents cheapest-first, not the same order -

def test_recovery_any_cheaper_option_reorders_by_price():
    state = _state_with_shortlist(_option("a", 1, 4000))
    state.focused_option = state.shortlist[0]
    state.rejected.append(Rejection(option_id="a", reason=RejectionReason.PRICE, turn_index=1))

    result = SearchResult(exact=[
        SearchHit(option_id="a", property_id="prop-a", property_name="Property 1", room_type_id="room-a",
                  room_type_name="Deluxe", city="Goa", area=None, star_tier=4, rooms_needed=1, nights=2,
                  price_per_night=4000, estimated_total=8000),
        SearchHit(option_id="b", property_id="prop-b", property_name="Property 2", room_type_id="room-b",
                  room_type_name="Deluxe", city="Goa", area=None, star_tier=4, rooms_needed=1, nights=2,
                  price_per_night=2500, estimated_total=5000),
        SearchHit(option_id="c", property_id="prop-c", property_name="Property 3", room_type_id="room-c",
                  room_type_name="Deluxe", city="Goa", area=None, star_tier=4, rooms_needed=1, nights=2,
                  price_per_night=3000, estimated_total=6000),
    ])
    _apply_search_result_to_state(state, result, cheapest_first=True)
    assert [o.option_id for o in state.shortlist] == ["b", "c", "a"]  # cheapest first; previously-rejected "a" sinks last
    assert state.shortlist[0].ordinal == 1  # re-numbered to match the new presentation order


class _NullRepo:
    """`resolve_selection`'s property/room-name matching also calls
    `repo.get_property`/`get_room_type`; these tests never mention a name, so
    a repo that always returns None is enough — no database needed.
    """

    def get_property(self, property_id: str):
        return None

    def get_room_type(self, room_type_id: str):
        return None
