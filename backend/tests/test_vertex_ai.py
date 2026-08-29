from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.llm import VertexAIClient, build_llm_client
from app.llm.base import LLMError


class _Answer(BaseModel):
    city: str


class _FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _fake_client(*outcomes):
    models = _FakeModels(outcomes)
    return SimpleNamespace(models=models), models


def test_complete_json_uses_system_instruction_and_pydantic_schema():
    fake, models = _fake_client(SimpleNamespace(parsed={"city": "Goa"}, text='{"city":"Goa"}'))
    client = VertexAIClient(client=fake, max_retries=0)

    assert client.complete_json(system="extract", user="Goa please", schema=_Answer) == _Answer(city="Goa")

    call = models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "Goa please"
    assert call["config"].system_instruction == "extract"
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is None
    assert call["config"].response_json_schema == _Answer.model_json_schema()


def test_complete_json_falls_back_to_response_text():
    fake, _models = _fake_client(SimpleNamespace(parsed=None, text='{"city":"Jaipur"}'))
    client = VertexAIClient(client=fake, max_retries=0)

    assert client.complete_json(system="extract", user="Jaipur", schema=_Answer) == _Answer(city="Jaipur")


def test_complete_text_retries_transport_failure():
    fake, models = _fake_client(RuntimeError("temporary failure"), SimpleNamespace(text="One option.", parsed=None))
    client = VertexAIClient(client=fake, max_retries=1)

    assert client.complete_text(system="respond", user="facts") == "One option."
    assert len(models.calls) == 2


def test_empty_response_is_an_llm_error():
    fake, _models = _fake_client(SimpleNamespace(text="", parsed=None))
    client = VertexAIClient(client=fake, max_retries=0)

    with pytest.raises(LLMError, match="empty response"):
        client.complete_text(system="respond", user="facts")


def test_factory_builds_vertex_express_client_without_network(monkeypatch: pytest.MonkeyPatch):
    init_calls = []

    def fake_google_client(**kwargs):
        init_calls.append(kwargs)
        return SimpleNamespace(models=SimpleNamespace())

    monkeypatch.setattr("app.llm.vertex.genai.Client", fake_google_client)
    client = build_llm_client(
        backend="vertex",
        model="gemini-2.5-flash",
        timeout_s=30,
        vertex_api_key="test-key",
    )

    assert isinstance(client, VertexAIClient)
    assert init_calls[0]["vertexai"] is True
    assert init_calls[0]["api_key"] == "test-key"
    assert "project" not in init_calls[0]
    assert init_calls[0]["http_options"].api_version == "v1"
    assert init_calls[0]["http_options"].timeout == 30_000


def test_factory_builds_standard_vertex_client_with_project_and_location(monkeypatch: pytest.MonkeyPatch):
    init_calls = []

    def fake_google_client(**kwargs):
        init_calls.append(kwargs)
        return SimpleNamespace(models=SimpleNamespace())

    monkeypatch.setattr("app.llm.vertex.genai.Client", fake_google_client)
    client = build_llm_client(
        backend="vertex",
        model="gemini-2.5-flash",
        timeout_s=45,
        vertex_project="mira-project",
        vertex_location="asia-south1",
    )

    assert isinstance(client, VertexAIClient)
    assert init_calls[0]["vertexai"] is True
    assert init_calls[0]["project"] == "mira-project"
    assert init_calls[0]["location"] == "asia-south1"
    assert init_calls[0]["credentials"] is None


def test_credential_file_can_supply_the_project(monkeypatch: pytest.MonkeyPatch):
    fake_credentials = object()
    auth_calls = []
    init_calls = []

    def fake_load_credentials(path, scopes):
        auth_calls.append((path, scopes))
        return fake_credentials, "project-from-credentials"

    monkeypatch.setattr("app.llm.vertex.load_credentials_from_file", fake_load_credentials)
    monkeypatch.setattr(
        "app.llm.vertex.genai.Client",
        lambda **kwargs: init_calls.append(kwargs) or SimpleNamespace(models=SimpleNamespace()),
    )

    VertexAIClient(credentials_file="/tmp/google-credentials.json")

    assert auth_calls == [
        ("/tmp/google-credentials.json", ["https://www.googleapis.com/auth/cloud-platform"])
    ]
    assert init_calls[0]["project"] == "project-from-credentials"
    assert init_calls[0]["credentials"] is fake_credentials


def test_api_key_and_credential_file_cannot_be_combined():
    with pytest.raises(ValueError, match="mutually exclusive"):
        VertexAIClient(api_key="test-key", credentials_file="credentials.json")
