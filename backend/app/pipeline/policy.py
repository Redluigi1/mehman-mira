"""Stage 3 — Decide (deterministic policy, plan §3 table). A readable
function from state (+ this turn's scratch context) to a single `NextAction`.
No LLM involved — this is exactly the decision-making the case study grades.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.state import ConversationState
from app.domain.trace import NextAction, NextActionType, UserAct
from app.pipeline.extract import Objection
from app.tools.types import PropertyPoliciesResult, RoomDetailsResult, SearchResult, SuggestedAddon

MIN_VIABLE_SET_MISSING_ORDER = ["destination", "dates", "party"]

# Actions whose tool result changes what the *final* action should be —
# decide() is consulted a second time after the tool runs.
NEEDS_REDECIDE_AFTER_ACT = {
    NextActionType.SEARCH, NextActionType.REFINE_SEARCH, NextActionType.ANSWER_FACTUAL,
    NextActionType.WIDEN_OR_ASK,
}
# Actions with exactly one tool call and no further branching on the result.
ONE_SHOT_TOOL_ACTIONS = {NextActionType.QUOTE, NextActionType.HOLD, NextActionType.UPSELL}


@dataclass
class TurnContext:
    user_act: UserAct
    objection: Objection | None = None
    is_question: bool = False
    question_about: str | None = None
    referent_mentions: list[str] = field(default_factory=list)

    last_search: SearchResult | None = None
    last_widen: SearchResult | None = None  # set once find_alternatives has run this turn (distinct from last_search: a plain search can legitimately come back empty and still need widening)
    last_policy_fact: PropertyPoliciesResult | None = None
    last_room_details: RoomDetailsResult | None = None
    question_target_property_id: str | None = None
    question_resolved: bool = False  # true once a lookup for this turn's question has run, even if target couldn't be resolved
    eligible_addons: list[SuggestedAddon] = field(default_factory=list)  # precomputed, upsell timing rule (Bonus 1)


def _missing_field(state: ConversationState) -> str | None:
    intent = state.intent
    if not intent.destination.is_set:
        return "destination"
    stay = intent.stay.value if intent.stay.is_set else None
    if stay is None or (stay.check_in is None and stay.check_out is None):
        return "dates"
    if stay.check_in is not None and stay.check_out is None:
        # check-in is already known — asking "dates" again from scratch would
        # ignore what the guest just said; the only gap left is how long
        # they're staying.
        return "duration"
    if stay.check_out is not None and stay.check_in is None:
        return "dates"
    if not intent.party.is_set or intent.party.value.adults is None:
        return "party"
    return None


def decide(state: ConversationState, ctx: TurnContext) -> NextAction:
    if ctx.user_act == UserAct.OTHER and not ctx.is_question and not state.intent.destination.is_set:
        return NextAction(type=NextActionType.DEFLECT, reason="unclassifiable message, nothing actionable extracted")

    unresolved_conflicts = [c for c in state.conflicts if not c.resolved]
    if unresolved_conflicts:
        return NextAction(type=NextActionType.RESOLVE_CONFLICT, reason=unresolved_conflicts[0].detail)

    if ctx.is_question:
        if not ctx.question_resolved:
            return NextAction(type=NextActionType.ANSWER_FACTUAL, ask_field=ctx.question_about,
                               reason="guest asked a factual question, looking it up")
        fact_is_unknown = (
            ctx.last_policy_fact is not None
            and any(p.status == "unknown" for p in ctx.last_policy_fact.policies)
        )
        if fact_is_unknown:
            return NextAction(type=NextActionType.SURFACE_UNKNOWN, reason="the dataset does not have this fact")
        return NextAction(type=NextActionType.ANSWER_FACTUAL, ask_field=ctx.question_about, reason="fact looked up")

    if state.hold is not None:
        return NextAction(type=NextActionType.ANSWER_FACTUAL, reason="booking already held")

    if state.quote is not None and ctx.user_act in (UserAct.SELECT, UserAct.ANSWER) and not ctx.objection:
        already_offered = state.upsell_offered_for_quote == state.quote.option_id
        if ctx.eligible_addons and not already_offered:
            return NextAction(type=NextActionType.UPSELL, reason="guest engaged with the quote, offering add-ons before the hold")
        if set(state.accepted_addon_ids) != set(state.quote_addon_ids):
            return NextAction(type=NextActionType.QUOTE, reason="add-on selection changed since the quote was built, rebuilding")
        return NextAction(type=NextActionType.HOLD, reason="guest accepted the quote")

    if ctx.objection is not None and ctx.last_search is None:
        return NextAction(type=NextActionType.REFINE_SEARCH, reason=f"objection: {ctx.objection.kind}")

    if state.focused_option is not None and state.quote is None:
        return NextAction(type=NextActionType.QUOTE, reason="option focused, building the quote")

    missing = _missing_field(state)
    if missing is not None:
        return NextAction(type=NextActionType.ASK, ask_field=missing, reason=f"{missing} not yet known")

    if not state.shortlist and ctx.last_search is None:
        return NextAction(type=NextActionType.SEARCH, reason="minimum viable search set present, searching")

    if ctx.last_search is not None:
        if ctx.last_search.exact:
            return NextAction(type=NextActionType.PRESENT, reason="exact matches found")
        if ctx.last_search.near_miss:
            return NextAction(type=NextActionType.PRESENT_ALTERNATIVES, reason="only near-miss matches found")
        return NextAction(type=NextActionType.WIDEN_OR_ASK, reason="no matches at all, even relaxed")

    if state.quote is not None:
        # Reaching here means every earlier branch already ruled out an
        # objection, a question, and a field-changing modify/new_request (any
        # of those would have cleared state.quote in reconcile.py or matched
        # a branch above). A quote is pending and nothing else claimed this
        # turn — the extractor's user_act classification (e.g. on casual
        # slang like "book it lesgooo") is the only ambiguous thing left, so
        # don't fall back to re-dumping the whole shortlist; treat it as
        # acceptance instead.
        already_offered = state.upsell_offered_for_quote == state.quote.option_id
        if ctx.eligible_addons and not already_offered:
            return NextAction(type=NextActionType.UPSELL, reason="quote pending, offering add-ons before the hold")
        if set(state.accepted_addon_ids) != set(state.quote_addon_ids):
            return NextAction(type=NextActionType.QUOTE, reason="add-on selection changed since the quote was built, rebuilding")
        return NextAction(type=NextActionType.HOLD, reason="quote pending and nothing else claimed this turn, treating as acceptance")

    if state.shortlist:
        return NextAction(type=NextActionType.PRESENT, reason="results already on hand")

    return NextAction(type=NextActionType.DEFLECT, reason="no actionable path found")
