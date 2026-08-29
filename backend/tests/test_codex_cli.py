from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.llm import build_llm_client
from app.llm.codex_cli import CodexCliClient


class _Answer(BaseModel):
    city: str


def _fake_run(final_message: str, calls: list):
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(final_message, encoding="utf-8")
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    return run


def test_complete_json_prompts_with_schema_and_validates(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr("app.llm.codex_cli.subprocess.run", _fake_run('{"city":"Goa"}', calls))

    client = CodexCliClient(model="gpt-5.6-terra", reasoning_effort="low", max_retries=0)
    answer = client.complete_json(system="extract", user="Goa please", schema=_Answer)

    assert answer == _Answer(city="Goa")
    cmd, kwargs = calls[0]
    assert cmd[:2] == [cmd[0], "exec"]
    assert cmd[cmd.index("--model") + 1] == "gpt-5.6-terra"
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in cmd
    assert "--ignore-user-config" in cmd
    assert "--output-schema" not in cmd
    assert '"city"' in kwargs["input"]
    assert kwargs["input"].find("\n<system_instructions>\n") < kwargs["input"].find("\n<user_input>\n")


def test_complete_text_reads_only_the_final_message(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr("app.llm.codex_cli.subprocess.run", _fake_run("Here is one option.", calls))

    client = CodexCliClient(max_retries=0)
    assert client.complete_text(system="respond", user="facts") == "Here is one option."
    assert "--output-schema" not in calls[0][0]


def test_backend_factory_defaults_to_codex_shape():
    client = build_llm_client(
        backend="codex_cli",
        model="gpt-5.6-terra",
        timeout_s=30,
        reasoning_effort="low",
    )
    assert isinstance(client, CodexCliClient)


def test_invalid_reasoning_effort_is_rejected():
    with pytest.raises(ValueError, match="unsupported Codex reasoning effort"):
        CodexCliClient(reasoning_effort="turbo")
