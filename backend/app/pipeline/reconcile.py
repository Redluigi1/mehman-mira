"""Stage 2 — Reconcile (deterministic). Applies the extractor's proposed
`StateDelta` to `ConversationState` with provenance. `modify` never resets —
only the specific slots named in `set_fields`/`clear_fields` change; every
other slot survives untouched, which is what makes "actually make that 4
people and one more night" an update rather than a restart.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.domain.intent import (
    Budget, BudgetBasis, BedType, ChildAge, Destination, GuestIntent, Occasion,
    Party, PolicyNeeds, PropertyType, RoomPrefs, Slot, StayWindow, TripPurpose, ViewType,
)
from app.domain.state import ConversationState, ReferentRegistry, Rejection, Stage
from app.pipeline.extract import StateDelta

DEFAULT_CONFIDENCE = 0.7


def _search_key(intent: GuestIntent) -> tuple:
    dest = intent.destination.value
    stay = intent.stay.value
    party = intent.party.value
    return (
        dest.city if dest else None,
        stay.check_in if stay else None,
        stay.check_out if stay else None,
        party.adults if party else None,
        len(party.children) if party else None,
    )


def _apply_field(intent: GuestIntent, path: str, value: Any, turn_index: int, confidence: float) -> None:
    top, _, rest = path.partition(".")

    if top == "destination":
        dest = intent.destination.value or Destination(city="")
        if rest == "city":
            dest.city = str(value)
        elif rest == "area":
            dest.area = str(value)
        elif rest == "flexible":
            dest.flexible = bool(value)
        else:
            return
        intent.destination = Slot(value=dest, confidence=confidence, source_turn=turn_index)

    elif top == "stay":
        stay = intent.stay.value or StayWindow()
        if rest == "nights":
            stay.nights = int(value)
        elif rest == "flex_days":
            stay.flex_days = int(value)
        elif rest == "check_in":
            stay.check_in = date.fromisoformat(str(value)).isoformat()
        elif rest == "check_out":
            stay.check_out = date.fromisoformat(str(value)).isoformat()
        else:
            return
        intent.stay = Slot(value=stay, confidence=confidence, source_turn=turn_index)

    elif top == "party":
        party = intent.party.value or Party()
        if rest == "adults":
            party.adults = int(value)
        elif rest == "children":
            party.children = [ChildAge(age=int(c["age"])) for c in value]
        elif rest == "rooms_needed":
            party.rooms_needed = int(value)
        else:
            return
        intent.party = Slot(value=party, confidence=confidence, source_turn=turn_index)

    elif top == "budget":
        budget = intent.budget.value or Budget(amount=0)
        if rest == "amount":
            budget.amount = float(value)
        elif rest == "basis":
            budget.basis = BudgetBasis(value)
        elif rest == "hard":
            budget.hard = bool(value)
        else:
            return
        intent.budget = Slot(value=budget, confidence=confidence, source_turn=turn_index)

    elif top == "property_prefs" and not rest:
        intent.property_prefs = Slot(value=[PropertyType(v) for v in value], confidence=confidence, source_turn=turn_index)

    elif top == "room_prefs":
        prefs = intent.room_prefs.value or RoomPrefs()
        if rest == "bed_type":
            prefs.bed_type = BedType(value)
        elif rest == "view":
            prefs.view = ViewType(value)
        elif rest == "private_pool":
            prefs.private_pool = bool(value)
        elif rest == "connecting_rooms":
            prefs.connecting_rooms = bool(value)
        else:
            return
        intent.room_prefs = Slot(value=prefs, confidence=confidence, source_turn=turn_index)

    elif top == "amenities_required" and not rest:
        intent.amenities_required = Slot(value=[str(v) for v in value], confidence=confidence, source_turn=turn_index)

    elif top == "amenities_nice" and not rest:
        intent.amenities_nice = Slot(value=[str(v) for v in value], confidence=confidence, source_turn=turn_index)

    elif top == "policy_needs":
        needs = intent.policy_needs.value or PolicyNeeds()
        if rest in ("smoking", "pets", "early_checkin", "late_checkout", "party_friendly"):
            setattr(needs, rest, bool(value))
        else:
            return
        intent.policy_needs = Slot(value=needs, confidence=confidence, source_turn=turn_index)

    elif top == "special_requirements" and not rest:
        intent.special_requirements = Slot(value=[str(v) for v in value], confidence=confidence, source_turn=turn_index)

    elif top == "trip_purpose" and not rest:
        intent.trip_purpose = Slot(value=TripPurpose(value), confidence=confidence, source_turn=turn_index)

    elif top == "occasion" and not rest:
        intent.occasion = Slot(value=Occasion(value), confidence=confidence, source_turn=turn_index)


_CLEARABLE_TOP_LEVEL = {
    "destination", "stay", "party", "budget", "property_prefs", "room_prefs",
    "amenities_required", "amenities_nice", "policy_needs", "special_requirements",
    "trip_purpose", "occasion",
}


def _clear_field(intent: GuestIntent, path: str) -> None:
    top = path.partition(".")[0]
    if top in _CLEARABLE_TOP_LEVEL:
        setattr(intent, top, Slot())


def apply_state_delta(state: ConversationState, delta: StateDelta, today: date, turn_index: int) -> ConversationState:
    state = state.model_copy(deep=True)
    state.turn_index = turn_index
    intent = state.intent
    before_key = _search_key(intent)
    had_budget_before = intent.budget.value is not None

    for path, value in delta.set_fields.items():
        try:
            _apply_field(intent, path, value, turn_index, delta.confidence.get(path, DEFAULT_CONFIDENCE))
        except (ValueError, TypeError, KeyError):
            continue  # a malformed proposal from the extractor never crashes the turn

    if not had_budget_before and intent.budget.value is not None and "budget.basis" not in delta.set_fields:
        # The guest gave a number but never said per-night or total — Budget's
        # own pydantic default (per_night) is filling the gap, not something
        # they stated. Flag it so the State panel can mark it an assumption
        # rather than presenting it as a known fact.
        intent.budget.is_assumption = True

    # check_in/check_out/nights were already set directly from the extractor's
    # resolved ISO dates above (Decision 022 — the LLM resolves calendar
    # anchors itself, no downstream regex/dateutil parsing of guest text).
    # The only thing left to derive here is a check_out the guest didn't
    # state explicitly this turn, from a check_in + nights that are known.
    stay = intent.stay.value
    if stay and stay.check_in and stay.nights and "stay.check_out" not in delta.set_fields:
        derived_check_out = (date.fromisoformat(stay.check_in) + timedelta(days=stay.nights)).isoformat()
        if derived_check_out != stay.check_out:
            stay = stay.model_copy()
            stay.check_out = derived_check_out
            intent.stay = Slot(value=stay, confidence=intent.stay.confidence, source_turn=turn_index)

    for path in delta.clear_fields:
        _clear_field(intent, path)

    intent.party_type = intent.derive_party_type()
    state.intent = intent

    after_key = _search_key(intent)
    if state.shortlist and after_key != before_key:
        state.shortlist = []
        state.referents = ReferentRegistry()
        state.focused_option = None
        state.quote = None
        state.stage = Stage.DISCOVER

    if delta.objection is not None and state.focused_option is not None:
        state.rejected.append(Rejection(
            option_id=state.focused_option.option_id, reason=delta.objection.kind, turn_index=turn_index,
        ))

    return state
