"""Web channel — the `ChannelAdapter` boundary (plan §11) applied to HTTP.
Routes are deliberately thin: they move JSON in and out of the
channel-agnostic `ConversationEngine`; all understanding happens there.
API surface per plan §10.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.domain.state import ConversationState
from app.domain.supply import Property
from app.domain.trace import NextAction, TurnTrace
from app.llm.base import LLMError
from app.pipeline.engine import ConversationEngine

router = APIRouter()


def _engine(request: Request) -> ConversationEngine:
    return request.app.state.engine


class CreateConversationResponse(BaseModel):
    conversation_id: str


class MessageRequest(BaseModel):
    text: str


class MessageResponse(BaseModel):
    reply: str
    state: ConversationState
    next_action: NextAction
    trace: TurnTrace
    errors: list[str]


class ConversationDetail(BaseModel):
    conversation_id: str
    turn_count: int
    snapshots: list[ConversationState]
    traces: list[TurnTrace]
    replies: list[str]


class TurnDetail(BaseModel):
    turn_index: int
    state: ConversationState
    trace: TurnTrace | None


@router.post("/conversations", response_model=CreateConversationResponse)
def create_conversation(request: Request) -> CreateConversationResponse:
    engine = _engine(request)
    conversation_id = f"web-{uuid.uuid4().hex[:12]}"
    engine.start_conversation(conversation_id)
    return CreateConversationResponse(conversation_id=conversation_id)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
def post_message(conversation_id: str, body: MessageRequest, request: Request) -> MessageResponse:
    engine = _engine(request)
    if not engine.store.exists(conversation_id):
        raise HTTPException(status_code=404, detail="unknown conversation_id — POST /conversations first")
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="message text must not be empty")
    try:
        reply, state, trace = engine.handle_message(conversation_id, body.text)
    except LLMError as exc:
        # Decision 003 is open: the dev backend shells out to a real CLI process,
        # which can time out or fail. Surface it as a typed error rather than a
        # bare 500 — the brief explicitly asks for errors to reach the UI, not
        # be swallowed (plan §10).
        raise HTTPException(status_code=503, detail=f"Mira is temporarily unavailable: {exc}") from exc
    return MessageResponse(reply=reply, state=state, next_action=trace.next_action, trace=trace, errors=trace.errors)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, request: Request) -> ConversationDetail:
    engine = _engine(request)
    if not engine.store.exists(conversation_id):
        raise HTTPException(status_code=404, detail="unknown conversation_id")
    snapshots = engine.store.get_snapshots(conversation_id)
    return ConversationDetail(
        conversation_id=conversation_id, turn_count=snapshots[-1].turn_index,
        snapshots=snapshots, traces=engine.store.get_traces(conversation_id),
        replies=engine.store.get_replies(conversation_id),
    )


@router.get("/conversations/{conversation_id}/turns/{turn_index}", response_model=TurnDetail)
def get_turn(conversation_id: str, turn_index: int, request: Request) -> TurnDetail:
    engine = _engine(request)
    if not engine.store.exists(conversation_id):
        raise HTTPException(status_code=404, detail="unknown conversation_id")
    try:
        state = engine.store.get_state(conversation_id, turn_index)
    except IndexError:
        raise HTTPException(status_code=404, detail=f"no such turn {turn_index}") from None
    trace = engine.store.get_trace(conversation_id, turn_index)
    return TurnDetail(turn_index=turn_index, state=state, trace=trace)


@router.get("/catalogue/properties/{property_id}", response_model=Property)
def get_property(property_id: str, request: Request) -> Property:
    engine = _engine(request)
    prop = engine.repo.get_property(property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="unknown property_id")
    return prop
