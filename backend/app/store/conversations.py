"""Append-only, in-memory conversation store (Decision 010). The event log is
the source of truth; per-turn state snapshots and traces are cached alongside
it as the engine produces them, so the Timeline / time-travel UI (GET
`/conversations/{id}/turns/{n}`) is a cheap lookup rather than a replay.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.events import ConversationEvent, GuestMessage
from app.domain.state import ConversationState
from app.domain.trace import TurnTrace


@dataclass
class _ConversationRecord:
    conversation_id: str
    events: list[ConversationEvent] = field(default_factory=list)
    snapshots: list[ConversationState] = field(default_factory=list)  # index == turn_index
    traces: list[TurnTrace] = field(default_factory=list)  # index == turn_index
    replies: list[str] = field(default_factory=list)  # index == turn_index - 1, Mira's reply text per turn


class ConversationStore:
    def __init__(self) -> None:
        self._records: dict[str, _ConversationRecord] = {}

    def create(self, conversation_id: str) -> ConversationState:
        if conversation_id in self._records:
            raise ValueError(f"conversation {conversation_id} already exists")
        state = ConversationState(conversation_id=conversation_id, turn_index=0)
        self._records[conversation_id] = _ConversationRecord(
            conversation_id=conversation_id, snapshots=[state]
        )
        return state

    def exists(self, conversation_id: str) -> bool:
        return conversation_id in self._records

    def _get(self, conversation_id: str) -> _ConversationRecord:
        record = self._records.get(conversation_id)
        if record is None:
            raise KeyError(f"unknown conversation {conversation_id}")
        return record

    def append_event(self, conversation_id: str, event: ConversationEvent) -> None:
        self._get(conversation_id).events.append(event)

    def append_turn(self, conversation_id: str, state: ConversationState, trace: TurnTrace) -> None:
        record = self._get(conversation_id)
        record.snapshots.append(state)
        record.traces.append(trace)

    def get_events(self, conversation_id: str) -> list[ConversationEvent]:
        return list(self._get(conversation_id).events)

    def append_reply(self, conversation_id: str, text: str) -> None:
        self._get(conversation_id).replies.append(text)

    def render_transcript(self, conversation_id: str, max_turns: int = 8) -> list[str]:
        record = self._get(conversation_id)
        guest_messages = [e for e in record.events if isinstance(e, GuestMessage)]
        lines: list[str] = []
        for i, msg in enumerate(guest_messages[-max_turns:]):
            lines.append(f"Guest: {msg.text}")
            idx = len(guest_messages) - max_turns + i if len(guest_messages) > max_turns else i
            if 0 <= idx < len(record.replies):
                lines.append(f"Mira: {record.replies[idx]}")
        return lines

    def get_state(self, conversation_id: str, turn_index: int | None = None) -> ConversationState:
        record = self._get(conversation_id)
        if turn_index is None:
            return record.snapshots[-1]
        return record.snapshots[turn_index]

    def get_trace(self, conversation_id: str, turn_index: int) -> TurnTrace | None:
        record = self._get(conversation_id)
        idx = turn_index - 1  # traces are recorded per turn, 1-indexed; snapshots include turn 0 (initial)
        if 0 <= idx < len(record.traces):
            return record.traces[idx]
        return None

    def latest_turn_index(self, conversation_id: str) -> int:
        return self._get(conversation_id).snapshots[-1].turn_index
