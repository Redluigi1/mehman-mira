"""Per-turn observability: what the agent decided and why, rendered by the
Trace panel. No chain of thought is ever included — structured decisions only.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class UserAct(str, Enum):
    NEW_REQUEST = "new_request"
    MODIFY = "modify"
    ANSWER = "answer"
    SELECT = "select"
    OBJECTION = "objection"
    QUESTION = "question"
    CHITCHAT = "chitchat"
    OTHER = "other"


class NextActionType(str, Enum):
    ASK = "ask"
    SEARCH = "search"
    PRESENT = "present"
    PRESENT_ALTERNATIVES = "present_alternatives"
    WIDEN_OR_ASK = "widen_or_ask"
    REFINE_SEARCH = "refine_search"
    ANSWER_FACTUAL = "answer_factual"
    SURFACE_UNKNOWN = "surface_unknown"
    RESOLVE_CONFLICT = "resolve_conflict"
    QUOTE = "quote"
    UPSELL = "upsell"
    HOLD = "hold"
    DEFLECT = "deflect"


class NextAction(BaseModel):
    type: NextActionType
    ask_field: str | None = None  # set when type == ASK
    reason: str = ""


class ToolCall(BaseModel):
    name: str
    args: dict
    result_summary: str
    latency_ms: float
    ok: bool = True
    error: str | None = None


class GroundingVerdict(str, Enum):
    CLEAN = "clean"
    REPAIRED = "repaired"
    FALLBACK = "fallback"


class TurnTrace(BaseModel):
    conversation_id: str
    turn_index: int
    user_act: UserAct
    next_action: NextAction
    tool_calls: list[ToolCall] = Field(default_factory=list)
    grounding_verdict: GroundingVerdict = GroundingVerdict.CLEAN
    errors: list[str] = Field(default_factory=list)
