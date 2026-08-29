"""The turn loop (plan §3). Two narrow LLM calls (extract, respond);
everything between them — reconciliation, conflict detection, next-action
choice, tool dispatch, grounding — is deterministic Python (Decision 001).
"""
from __future__ import annotations

from datetime import date

from app.data.indexes import CityIndex
from app.data.repo import Repo
from app.domain.events import GuestMessage
from app.domain.intent import PartyType
from app.domain.state import ConversationState, Stage
from app.domain.trace import NextAction, NextActionType, TurnTrace
from app.llm.base import LLMClient
from app.logging_config import turn_logger
from app.pipeline.act import TurnServices, run_action
from app.pipeline.addon_selection import resolve_addon_response
from app.pipeline.conflicts import sync_conflicts
from app.pipeline.extract import extract_state_delta
from app.pipeline.ground import build_grounding_packet
from app.pipeline.policy import NEEDS_REDECIDE_AFTER_ACT, ONE_SHOT_TOOL_ACTIONS, TurnContext, decide
from app.pipeline.reconcile import apply_state_delta
from app.pipeline.referents import resolve_selection
from app.pipeline.respond import generate_response
from app.pipeline.safety import looks_like_injection
from app.store.conversations import ConversationStore
from app.store.holds import HoldStore
from app.tools.registry import build_default_registry
from app.tools.types import SuggestAddonsArgs

MAX_DECIDE_ITERATIONS = 4

_STAGE_FOR_ACTION = {
    NextActionType.SEARCH: Stage.SEARCH,
    NextActionType.PRESENT: Stage.PRESENT,
    NextActionType.PRESENT_ALTERNATIVES: Stage.PRESENT,
    NextActionType.REFINE_SEARCH: Stage.NEGOTIATE,
    NextActionType.QUOTE: Stage.NEGOTIATE,
    NextActionType.HOLD: Stage.HELD,
}


def _tool_already_ran(action_type: NextActionType, ctx: TurnContext) -> bool:
    if action_type == NextActionType.WIDEN_OR_ASK:
        return ctx.last_widen is not None
    if action_type in (NextActionType.SEARCH, NextActionType.REFINE_SEARCH):
        return ctx.last_search is not None
    if action_type == NextActionType.ANSWER_FACTUAL:
        return ctx.question_resolved
    return True


def _render_state_summary(state: ConversationState) -> str:
    intent = state.intent
    lines: list[str] = []
    if intent.destination.is_set:
        d = intent.destination.value
        lines.append(f"destination: {d.city}" + (f" ({d.area})" if d.area else ""))
    if intent.stay.is_set:
        s = intent.stay.value
        lines.append(f"dates: {s.check_in or '?'} to {s.check_out or '?'}" + (f", {s.nights} nights" if s.nights else ""))
    if intent.party.is_set:
        p = intent.party.value
        lines.append(f"party: {p.adults if p.adults is not None else '?'} adults" + (f", {len(p.children)} children" if p.children else ""))
    if intent.budget.is_set:
        b = intent.budget.value
        lines.append(f"budget: {b.amount} ({b.basis.value}{', hard limit' if b.hard else ''})")
    if intent.room_prefs.is_set and intent.room_prefs.value:
        rp = intent.room_prefs.value
        prefs = [x for x in [
            "private pool" if rp.private_pool else None,
            f"{rp.bed_type.value} bed" if rp.bed_type else None,
            f"{rp.view.value} view" if rp.view else None,
        ] if x]
        if prefs:
            lines.append("room prefs: " + ", ".join(prefs))
    if intent.amenities_required.is_set and intent.amenities_required.value:
        lines.append("amenities required: " + ", ".join(intent.amenities_required.value))
    if state.shortlist:
        lines.append(f"{len(state.shortlist)} option(s) currently shown to the guest")
        for option in state.shortlist:
            lines.append(
                f"shown option #{option.ordinal}: {option.property_name} — {option.room_type_name}"
            )
    if state.focused_option:
        lines.append(f"guest is focused on option #{state.focused_option.ordinal} ({state.focused_option.property_name})")
    if state.quote:
        lines.append(f"a quote has been built, total {state.quote.total}")
    if state.hold:
        lines.append("a booking hold already exists")
    return "\n".join(lines) if lines else "(nothing known yet)"


class ConversationEngine:
    def __init__(self, llm: LLMClient, repo: Repo, city_index: CityIndex, hold_store: HoldStore,
                 store: ConversationStore, today: date):
        self.llm = llm
        self.repo = repo
        self.city_index = city_index
        self.hold_store = hold_store
        self.store = store
        self.today = today
        self.registry = build_default_registry(repo, city_index, hold_store, today)

    def start_conversation(self, conversation_id: str) -> ConversationState:
        return self.store.create(conversation_id)

    def handle_message(self, conversation_id: str, text: str) -> tuple[str, ConversationState, TurnTrace]:
        if not self.store.exists(conversation_id):
            self.start_conversation(conversation_id)

        state = self.store.get_state(conversation_id)
        turn_index = state.turn_index + 1
        log = turn_logger(__name__, conversation_id, turn_index)
        log.info("turn started")
        self.store.append_event(conversation_id, GuestMessage(
            conversation_id=conversation_id, turn_index=turn_index, text=text,
        ))

        history = self.store.render_transcript(conversation_id)
        state_summary = _render_state_summary(state)
        delta = extract_state_delta(
            self.llm, history=history, state_summary=state_summary, today=self.today,
            turn_index=turn_index, latest_message=text,
        )

        state = apply_state_delta(state, delta, self.today, turn_index)

        selected = None
        if delta.selected_option_ordinal is not None:
            # The LLM performs semantic interpretation over the displayed
            # options; code constrains its proposal to an ordinal that really
            # exists in the current referent registry.
            selected = state.referents.by_ordinal(delta.selected_option_ordinal)
        elif delta.referent_mentions:
            # Backward-compatible exact/ordinal resolution for scripted evals
            # and straightforward extractor output.
            selected = resolve_selection(state, delta.referent_mentions, self.repo)

        if selected is not None:
            if selected is not None and (state.focused_option is None or selected.option_id != state.focused_option.option_id):
                state.focused_option = selected
                # Switching options invalidates any quote/hold/upsell state built
                # for the *previous* one — otherwise "what about the other one?"
                # would silently accept-or-upsell against a stale, wrong-option quote.
                state.quote = None
                state.hold = None
                state.upsell_offered_for_quote = None
                state.accepted_addon_ids = []
                state.quote_addon_ids = []

        sync_conflicts(state, self.repo, self.today)

        services = TurnServices(repo=self.repo, city_index=self.city_index, hold_store=self.hold_store,
                                 today=self.today, registry=self.registry)

        eligible_addons: list = []
        if state.quote is not None and state.focused_option is not None:
            party = state.intent.party.value
            addon_args = SuggestAddonsArgs(
                property_id=state.focused_option.property_id,
                party_type=state.intent.party_type.value if state.intent.party_type != PartyType.UNKNOWN else None,
                trip_purpose=state.intent.trip_purpose.value.value if state.intent.trip_purpose.value else None,
                occasion=state.intent.occasion.value.value if state.intent.occasion.value else None,
                guests_for_addons=party.total_guests if party else 1,
            )
            eligible_addons = self.registry.get("suggest_addons").fn(addon_args).suggestions

            # Only read the guest's reply as an add-on decision once the
            # offer has actually been made — otherwise an unrelated mention
            # of, say, "breakfast" earlier in the trip planning would be
            # misread as accepting an upsell that was never offered.
            if eligible_addons and state.upsell_offered_for_quote == state.quote.option_id:
                state.accepted_addon_ids = resolve_addon_response(text, eligible_addons, state.accepted_addon_ids)

        ctx = TurnContext(
            user_act=delta.user_act, objection=delta.objection, is_question=delta.is_question,
            question_about=delta.question_about, referent_mentions=delta.referent_mentions,
            eligible_addons=eligible_addons,
        )

        tool_calls = []
        if looks_like_injection(text):
            # Deterministic backstop (Decision 001/015, plan §12 EC8): never trust the
            # extractor's own judgment for something this consequential. No tool runs.
            action = NextAction(type=NextActionType.DEFLECT, reason="message matched the deterministic injection guard")
            log.info("injection guard triggered, deflecting without running any tool")
        else:
            action = decide(state, ctx)
            for _ in range(MAX_DECIDE_ITERATIONS):
                if action.type in NEEDS_REDECIDE_AFTER_ACT and not _tool_already_ran(action.type, ctx):
                    tc = run_action(action, state, ctx, services)
                    if tc is not None:
                        tool_calls.append(tc)
                        log.info("tool call: %s ok=%s %s", tc.name, tc.ok, tc.result_summary)
                    action = decide(state, ctx)
                    continue
                break

            if action.type in ONE_SHOT_TOOL_ACTIONS:
                tc = run_action(action, state, ctx, services)
                if tc is not None:
                    tool_calls.append(tc)
                    log.info("tool call: %s ok=%s %s", tc.name, tc.ok, tc.result_summary)

        state.stage = _STAGE_FOR_ACTION.get(action.type, state.stage)

        packet = build_grounding_packet(state, ctx, action)
        packet.tool_errors = [tc.error for tc in tool_calls if tc.error]
        tone_hint = state.intent.party_type.value if state.intent.party_type != PartyType.UNKNOWN else None
        reply_text, verdict = generate_response(self.llm, packet, tone_hint)

        trace = TurnTrace(
            conversation_id=conversation_id, turn_index=turn_index, user_act=delta.user_act,
            next_action=action, tool_calls=tool_calls, grounding_verdict=verdict,
            errors=[tc.error for tc in tool_calls if tc.error],
        )

        self.store.append_turn(conversation_id, state, trace)
        self.store.append_reply(conversation_id, reply_text)
        log.info("turn completed: next_action=%s grounding=%s stage=%s",
                  action.type.value, verdict.value, state.stage.value)
        return reply_text, state, trace
