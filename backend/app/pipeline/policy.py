"""Stage 3 — Decide (deterministic policy, plan §3 table). A readable
function from state (+ this turn's scratch context) to a single `NextAction`.
No LLM involved — this is exactly the decision-making the case study grades.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.state import ConversationState
from app.domain.trace import NextAction, NextActionType, UserAct
from app.pipeline.extract import Objection
from app.tools.types import PropertyPoliciesResult, RoomDetailsResult, SearchResult

MIN_VIABLE_SET_MISSING_ORDER = ["destination", "dates", "party"]

# Actions whose tool result changes what the *final* action should be —
# decide() is consulted a second time after the tool runs.
NEEDS_REDECIDE_AFTER_ACT = {NextActionType.SEARCH, NextActionType.REFINE_SEARCH, NextActionType.ANSWER_FACTUAL}
# Actions with exactly one tool call and no further branching on the result.
ONE_SHOT_TOOL_ACTIONS = {NextActionType.QUOTE, NextActionType.HOLD}


@dataclass
class TurnContext:
    user_act: UserAct
    objection: Objection | None = None
    is_question: bool = False
    question_about: str | None = None
    referent_mentions: list[str] = field(default_factory=list)

    last_search: SearchResult | None = None
    last_policy_fact: PropertyPoliciesResult | None = None
    last_room_details: RoomDetailsResult | None = None
    question_target_property_id: str | None = None
    question_resolved: bool = False  # true once a lookup for this turn's question has run, even if target couldn't be resolved


def _missing_field(state: ConversationState) -> str | None:
    intent = state.intent
    if not intent.destination.is_set:
        return "destination"
    if not intent.stay.is_set or intent.stay.value.check_in is None or intent.stay.value.check_out is None:
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

    if state.shortlist:
        return NextAction(type=NextActionType.PRESENT, reason="results already on hand")

    return NextAction(type=NextActionType.DEFLECT, reason="no actionable path found")
