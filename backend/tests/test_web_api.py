"""Web channel (Phase 4, plan §10) — exercises the actual FastAPI app, with
the real Claude CLI swapped for a scripted fake so the suite needs no
credentials and no subprocess (same rationale as `evals/README.md`).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.trace import UserAct
from app.llm.base import LLMClient, LLMError
from app.main import app


class _FakeLLM(LLMClient):
    def complete_json(self, *, system: str, user: str, schema):
        return schema(user_act=UserAct.NEW_REQUEST, set_fields={"destination.city": "Goa", "party.adults": 2},
                       date_expression="in 5 days for 2 nights")

    def complete_text(self, *, system: str, user: str) -> str:
        raise LLMError("force deterministic template fallback for the test")


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.app.state.engine.llm = _FakeLLM()
        yield c


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_conversation_lifecycle(client: TestClient):
    conv = client.post("/conversations").json()
    conversation_id = conv["conversation_id"]
    assert conversation_id.startswith("web-")

    resp = client.post(f"/conversations/{conversation_id}/messages", json={"text": "Goa for 2 of us in 5 days for 2 nights."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["next_action"]["type"] == "present"
    assert body["state"]["intent"]["destination"]["value"]["city"] == "Goa"
    assert len(body["trace"]["tool_calls"]) >= 1

    detail = client.get(f"/conversations/{conversation_id}").json()
    assert detail["turn_count"] == 1
    assert len(detail["snapshots"]) == 2  # turn 0 (initial) + turn 1

    turn = client.get(f"/conversations/{conversation_id}/turns/1").json()
    assert turn["trace"]["next_action"]["type"] == "present"


def test_unknown_conversation_returns_404(client: TestClient):
    assert client.post("/conversations/does-not-exist/messages", json={"text": "hi"}).status_code == 404
    assert client.get("/conversations/does-not-exist").status_code == 404


def test_empty_message_returns_422(client: TestClient):
    conversation_id = client.post("/conversations").json()["conversation_id"]
    resp = client.post(f"/conversations/{conversation_id}/messages", json={"text": "   "})
    assert resp.status_code == 422


def test_unknown_property_returns_404(client: TestClient):
    assert client.get("/catalogue/properties/does-not-exist").status_code == 404


def test_known_property_returns_record(client: TestClient):
    resp = client.get("/catalogue/properties/goa-edge-villa8")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Grand Dunes Villa"
