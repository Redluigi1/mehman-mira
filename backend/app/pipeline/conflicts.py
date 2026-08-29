"""Stage 2b — Conflict engine (plan §3/§12, Phase 3, Decision 014). Runs right
after reconcile: flags capacity, budget, policy, min-stay, past-date and
contradiction conflicts so `policy.decide()` can halt on `RESOLVE_CONFLICT`
before quoting or holding something the guest never actually agreed to.

Two tiers, deliberately different lifetimes:

- "hard" conflicts (`PAST_DATE`, `CONTRADICTION`) are pure functions of the
  guest's stated intent. They reappear every turn until the field that caused
  them actually changes — there is nothing to "acknowledge", the request is
  simply unusable as stated.
- "soft" conflicts (`CAPACITY`, `BUDGET`, `POLICY`, `MIN_STAY`) are checked
  against whatever option the guest is currently focused on. Mira gets
  exactly one turn to flag the tradeoff; if the same conflict (same option,
  same kind) is still present next turn, it is treated as accepted — the
  guest either fixes it (search key changes, option changes) or moves on.
  An explicit objection is handled separately by the existing
  rejection/`REFINE_SEARCH` path in `policy.decide()`, which fires precisely
  because the conflict is no longer blocking by then.
"""
from __future__ import annotations

from datetime import date

from app.data.repo import Repo
from app.domain.intent import BudgetBasis
from app.domain.state import Conflict, ConflictKind, ConversationState

_HARD_KINDS = {ConflictKind.PAST_DATE, ConflictKind.CONTRADICTION}


def _hard_conflicts(state: ConversationState, today: date) -> list[Conflict]:
    conflicts: list[Conflict] = []
    stay = state.intent.stay.value

    if stay and stay.check_in:
        check_in = date.fromisoformat(stay.check_in)
        if check_in < today:
            conflicts.append(Conflict(
                kind=ConflictKind.PAST_DATE,
                detail=f"requested check-in {stay.check_in} is before today ({today.isoformat()})",
                field_paths=["stay.check_in"],
            ))
        if stay.check_out and date.fromisoformat(stay.check_out) <= check_in:
            conflicts.append(Conflict(
                kind=ConflictKind.CONTRADICTION,
                detail=f"check-out {stay.check_out} is not after check-in {stay.check_in}",
                field_paths=["stay.check_in", "stay.check_out"],
            ))

    party = state.intent.party.value
    if party is not None and party.adults is not None and party.adults <= 0:
        conflicts.append(Conflict(
            kind=ConflictKind.CONTRADICTION, detail="party has zero or negative adults",
            field_paths=["party.adults"],
        ))

    budget = state.intent.budget.value
    if budget is not None and budget.amount <= 0:
        conflicts.append(Conflict(
            kind=ConflictKind.CONTRADICTION, detail="stated budget is zero or negative",
            field_paths=["budget.amount"],
        ))

    return conflicts


def _soft_conflicts(state: ConversationState, repo: Repo) -> list[Conflict]:
    option = state.focused_option
    if option is None:
        return []
    conflicts: list[Conflict] = []
    tag = f"focused_option:{option.option_id}"

    room = repo.get_room_type(option.room_type_id)
    party = state.intent.party.value
    if room is not None and party is not None and party.adults is not None:
        total_guests = party.total_guests
        capacity = room.max_occupancy * option.rooms_needed
        if total_guests > capacity:
            conflicts.append(Conflict(
                kind=ConflictKind.CAPACITY,
                detail=(f"{option.room_type_name} sleeps {capacity} across {option.rooms_needed} room(s), "
                        f"party is now {total_guests}"),
                field_paths=[tag, "party"],
            ))

    needs = state.intent.policy_needs.value
    if needs is not None:
        for key, required in (
            ("smoking", needs.smoking), ("pets", needs.pets), ("party_friendly", needs.party_friendly),
        ):
            if required is not True:
                continue
            policy = repo.get_policy(option.property_id, key)
            if policy.status == "known" and policy.value is False:
                conflicts.append(Conflict(
                    kind=ConflictKind.POLICY,
                    detail=f"{option.property_name} does not allow {key.replace('_', ' ')}",
                    field_paths=[tag, f"policy_needs.{key}"],
                ))

    budget = state.intent.budget.value
    if budget is not None and budget.hard:
        ceiling = budget.amount * option.nights if budget.basis == BudgetBasis.PER_NIGHT else budget.amount
        if option.estimated_total > ceiling:
            conflicts.append(Conflict(
                kind=ConflictKind.BUDGET,
                detail=(f"{option.property_name} comes to ₹{option.estimated_total:,.0f}, "
                        f"over the stated ceiling of ₹{ceiling:,.0f}"),
                field_paths=[tag, "budget"],
            ))

    stay = state.intent.stay.value
    if stay and stay.check_in and stay.check_out:
        check_in, check_out = date.fromisoformat(stay.check_in), date.fromisoformat(stay.check_out)
        rates = repo.get_rates(option.room_type_id, check_in, check_out)
        min_stay = max((r.min_stay for r in rates), default=1)
        if option.nights < min_stay:
            conflicts.append(Conflict(
                kind=ConflictKind.MIN_STAY,
                detail=f"{option.property_name} requires a {min_stay}-night minimum, you asked for {option.nights}",
                field_paths=[tag, "stay.nights"],
            ))

    return conflicts


def detect_conflicts(state: ConversationState, repo: Repo, today: date) -> list[Conflict]:
    return _hard_conflicts(state, today) + _soft_conflicts(state, repo)


def _conflict_key(c: Conflict) -> tuple:
    return (c.kind, tuple(c.field_paths))


def sync_conflicts(state: ConversationState, repo: Repo, today: date) -> None:
    """Recompute `state.conflicts` for this turn in place, carrying forward
    the "surfaced once" acknowledgement for soft conflicts (see module
    docstring). Hard conflicts get no such grace.
    """
    previously_surfaced = {_conflict_key(c) for c in state.conflicts}
    fresh = detect_conflicts(state, repo, today)
    for c in fresh:
        if c.kind in _HARD_KINDS:
            continue
        if _conflict_key(c) in previously_surfaced:
            c.resolved = True
    state.conflicts = fresh
