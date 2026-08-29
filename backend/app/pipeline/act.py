"""Stage 4 — Act. Dispatches the decided `NextAction` to the one tool it
needs (if any), applies the result onto `ConversationState`, and returns the
`ToolCall` trace record. Deterministic Python throughout (Decision 001);
failures are typed and never crash the turn.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

from app.data.indexes import CityIndex
from app.data.repo import Repo
from app.domain.state import BookingHold, ConversationState, OptionRef, Quote, QuoteLineItem, RejectionReason
from app.domain.trace import NextAction, NextActionType, ToolCall
from app.pipeline.policy import TurnContext
from app.pipeline.referents import resolve_target_property
from app.store.holds import HoldStore
from app.tools.capacity import extra_beds_needed, rooms_needed_for
from app.tools.registry import ToolRegistry, build_default_registry
from app.tools.types import (
    BookingHoldArgs, PropertyPoliciesArgs, QuoteArgs, RoomDetailsArgs, SearchArgs,
)

MAX_REFERENTS = 8


@dataclass
class TurnServices:
    repo: Repo
    city_index: CityIndex
    hold_store: HoldStore
    today: date
    registry: ToolRegistry = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = build_default_registry(self.repo, self.city_index, self.hold_store, self.today)


def _timed(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - start) * 1000


def _search_args_from_state(state: ConversationState) -> SearchArgs:
    intent = state.intent
    dest, stay, party = intent.destination.value, intent.stay.value, intent.party.value
    budget, prefs, needs = intent.budget.value, intent.room_prefs.value, intent.policy_needs.value
    return SearchArgs(
        city=dest.city, check_in=stay.check_in, check_out=stay.check_out,
        adults=party.adults or 1, children_ages=[c.age for c in party.children],
        budget_amount=budget.amount if budget else None,
        budget_basis=budget.basis.value if budget else None,
        property_types=intent.property_prefs.value or [],
        amenities_required=intent.amenities_required.value or [],
        smoking=needs.smoking if needs else None, pets=needs.pets if needs else None,
        bed_type=prefs.bed_type if prefs else None, view=prefs.view if prefs else None,
        private_pool=prefs.private_pool if prefs else None,
    )


def _apply_search_result_to_state(state: ConversationState, result, cheapest_first: bool = False) -> None:
    hits = result.exact + result.near_miss
    if cheapest_first:
        rejected_ids = {r.option_id for r in state.rejected}
        current = state.focused_option.option_id if state.focused_option else None
        hits = sorted(hits, key=lambda h: (h.option_id in rejected_ids or h.option_id == current, h.price_per_night))
    hits = hits[:MAX_REFERENTS]
    options = [
        OptionRef(
            option_id=h.option_id, property_id=h.property_id, room_type_id=h.room_type_id, ordinal=i + 1,
            property_name=h.property_name, room_type_name=h.room_type_name, city=h.city, area=h.area,
            star_tier=h.star_tier, rooms_needed=h.rooms_needed, nights=h.nights,
            price_per_night=h.price_per_night, estimated_total=h.estimated_total, relaxations=h.relaxations,
        )
        for i, h in enumerate(hits)
    ]
    state.shortlist = options
    state.referents = state.referents.replace(options)


def _do_search(state: ConversationState, ctx: TurnContext, services: TurnServices) -> ToolCall:
    args = _search_args_from_state(state)
    result, latency = _timed(services.registry.get("search_properties").fn, args)
    ctx.last_search = result
    # Recovery behaviour: "any cheaper option?" is an objection of kind price
    # re-triggering a plain search (policy.py) — re-rank cheapest-first rather
    # than returning the same order the guest already pushed back on.
    cheapest_first = ctx.objection is not None and ctx.objection.kind == RejectionReason.PRICE
    _apply_search_result_to_state(state, result, cheapest_first=cheapest_first)
    return ToolCall(
        name="search_properties", args=args.model_dump(mode="json"),
        result_summary=f"{len(result.exact)} exact, {len(result.near_miss)} near-miss", latency_ms=latency,
    )


def _do_widen(state: ConversationState, ctx: TurnContext, services: TurnServices) -> ToolCall:
    args = _search_args_from_state(state)
    result, latency = _timed(services.registry.get("find_alternatives").fn, args)
    ctx.last_search = result
    ctx.last_widen = result
    _apply_search_result_to_state(state, result)
    return ToolCall(
        name="find_alternatives", args=args.model_dump(mode="json"),
        result_summary=f"{len(result.exact)} exact, {len(result.near_miss)} near-miss via '{result.strategy}'",
        latency_ms=latency,
    )


def _answer_question(state: ConversationState, ctx: TurnContext, services: TurnServices) -> ToolCall | None:
    property_id = resolve_target_property(state, ctx.referent_mentions, services.repo)
    ctx.question_resolved = True
    ctx.question_target_property_id = property_id
    if property_id is None:
        return None

    qa = ctx.question_about or "other"
    if qa.startswith("policy."):
        key = qa.split(".", 1)[1]
        args = PropertyPoliciesArgs(property_id=property_id, keys=[key])
        result, latency = _timed(services.registry.get("get_property_policies").fn, args)
        ctx.last_policy_fact = result
        status = result.policies[0].status if result and result.policies else "n/a"
        return ToolCall(name="get_property_policies", args=args.model_dump(mode="json"),
                         result_summary=f"{key}: {status}", latency_ms=latency, ok=result is not None,
                         error=None if result else "property not found")

    if qa.startswith("room.") or qa in ("availability",):
        option = state.focused_option or (state.shortlist[0] if len(state.shortlist) == 1 else None)
        if option is None:
            return None
        args = RoomDetailsArgs(room_type_id=option.room_type_id)
        result, latency = _timed(services.registry.get("get_room_details").fn, args)
        ctx.last_room_details = result
        return ToolCall(name="get_room_details", args=args.model_dump(mode="json"),
                         result_summary="fetched" if result else "not found", latency_ms=latency,
                         ok=result is not None, error=None if result else "room not found")

    return None


def _build_quote(state: ConversationState, services: TurnServices) -> ToolCall | None:
    option = state.focused_option
    if option is None:
        return None
    room = services.repo.get_room_type(option.room_type_id)
    stay = state.intent.stay.value
    party = state.intent.party.value
    if room is None or stay is None or party is None:
        return None

    total_guests = (party.adults or 0) + len(party.children)
    rooms_needed = rooms_needed_for(total_guests, room.max_occupancy)
    extra_beds = extra_beds_needed(room, total_guests, rooms_needed)
    args = QuoteArgs(
        option_id=option.option_id, property_id=option.property_id, room_type_id=option.room_type_id,
        check_in=stay.check_in, check_out=stay.check_out, rooms_needed=rooms_needed,
        extra_beds=extra_beds, add_on_ids=[], guests_for_addons=total_guests,
    )
    result, latency = _timed(services.registry.get("calculate_quote").fn, args)
    if result is None:
        return ToolCall(name="calculate_quote", args=args.model_dump(mode="json"), result_summary="failed",
                         latency_ms=latency, ok=False, error="incomplete rate data for requested dates")

    state.quote = Quote(
        option_id=result.option_id, nights=result.nights, room_subtotal=result.room_subtotal,
        line_items=[QuoteLineItem(label=li.label, amount=li.amount) for li in result.line_items],
        taxes=result.taxes, fixed_fees=result.fixed_fees, total=result.total, currency=result.currency,
    )
    return ToolCall(name="calculate_quote", args=args.model_dump(mode="json"),
                     result_summary=f"total {result.total} {result.currency}", latency_ms=latency)


def _create_hold(state: ConversationState, services: TurnServices) -> ToolCall | None:
    quote = state.quote
    if quote is None:
        return None
    idempotency_key = f"{state.conversation_id}:{quote.option_id}:{quote.total}"
    args = BookingHoldArgs(option_id=quote.option_id, quote_total=quote.total, idempotency_key=idempotency_key)
    result, latency = _timed(services.registry.get("create_booking_hold").fn, args)
    state.hold = BookingHold(
        hold_id=result.hold_id, option_id=result.option_id, quote_total=result.quote_total,
        idempotency_key=result.idempotency_key, expires_at=result.expires_at,
    )
    return ToolCall(name="create_booking_hold", args=args.model_dump(mode="json"),
                     result_summary=f"hold {result.hold_id}" + (" (reused)" if result.reused_existing else ""),
                     latency_ms=latency)


def _do_upsell(state: ConversationState, ctx: TurnContext) -> ToolCall | None:
    if state.quote is None:
        return None
    state.upsell_offered_for_quote = state.quote.option_id
    names = ", ".join(a.name for a in ctx.eligible_addons)
    return ToolCall(
        name="suggest_addons", args={"property_id": state.focused_option.property_id if state.focused_option else ""},
        result_summary=f"suggested: {names}" if names else "no eligible add-ons", latency_ms=0.0,
    )


def run_action(action: NextAction, state: ConversationState, ctx: TurnContext, services: TurnServices) -> ToolCall | None:
    try:
        if action.type in (NextActionType.SEARCH, NextActionType.REFINE_SEARCH):
            return _do_search(state, ctx, services)
        if action.type == NextActionType.WIDEN_OR_ASK:
            return _do_widen(state, ctx, services)
        if action.type == NextActionType.ANSWER_FACTUAL and not ctx.question_resolved:
            return _answer_question(state, ctx, services)
        if action.type == NextActionType.QUOTE:
            return _build_quote(state, services)
        if action.type == NextActionType.HOLD:
            return _create_hold(state, services)
        if action.type == NextActionType.UPSELL:
            return _do_upsell(state, ctx)
        return None
    except Exception as exc:  # noqa: BLE001 — a tool failure must never crash the turn
        return ToolCall(name=action.type.value, args={}, result_summary="tool error", latency_ms=0.0,
                         ok=False, error=str(exc))
