"""Event-sourced conversation log (Decision 010). State at turn n is a fold
over events up to n. Guest messages and system events are the same kind of
input, which is the precondition for async escalation (Decision 011).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, Field


class EventType(str, Enum):
    GUEST_MESSAGE = "guest_message"
    SYSTEM_EVENT = "system_event"
    OWNER_REPLY = "owner_reply"  # reserved for Phase 7


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GuestMessage(BaseModel):
    type: Literal[EventType.GUEST_MESSAGE] = EventType.GUEST_MESSAGE
    conversation_id: str
    turn_index: int
    text: str
    channel: str = "cli"
    at: str = Field(default_factory=_now_iso)


class SystemEvent(BaseModel):
    type: Literal[EventType.SYSTEM_EVENT] = EventType.SYSTEM_EVENT
    conversation_id: str
    turn_index: int
    kind: str  # e.g. "hold_expired", "state_reset"
    detail: dict = Field(default_factory=dict)
    at: str = Field(default_factory=_now_iso)


class OwnerReply(BaseModel):
    """Reserved for Phase 7 (Decision 011). Not produced by anything yet."""

    type: Literal[EventType.OWNER_REPLY] = EventType.OWNER_REPLY
    conversation_id: str
    turn_index: int
    property_id: str
    question_key: str
    answer: str
    at: str = Field(default_factory=_now_iso)


ConversationEvent = Union[GuestMessage, SystemEvent, OwnerReply]
