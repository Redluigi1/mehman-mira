"""YAML case schema (plan §13). Each case is a scripted conversation: guest
messages, the extraction each one should produce (standing in for the LLM,
see `evals/README.md`), and per-turn assertions the deterministic pipeline
must satisfy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ScriptedDelta(BaseModel):
    user_act: str = "new_request"
    set_fields: dict[str, Any] = Field(default_factory=dict)
    clear_fields: list[str] = Field(default_factory=list)
    referent_mentions: list[str] = Field(default_factory=list)
    date_expression: str | None = None
    objection: dict[str, str] | None = None
    is_question: bool = False
    question_about: str | None = None


class TurnAssertions(BaseModel):
    next_action: str | None = None
    tools_called: list[str] | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    price_total: float | None = None
    top3_property_id: str | None = None
    shortlist_contains: str | None = None
    grounding_verdict: str | None = None
    must_not_say: list[str] = Field(default_factory=list)


class EvalTurn(BaseModel):
    guest_message: str
    extracted_delta: ScriptedDelta
    scripted_reply: str | None = None  # None -> force LLMError -> deterministic template fallback
    assert_: TurnAssertions = Field(default_factory=TurnAssertions, alias="assert")

    model_config = {"populate_by_name": True}


class EvalCase(BaseModel):
    id: str
    description: str
    conversation_id: str
    turns: list[EvalTurn]


def load_cases(cases_dir: Path) -> list[EvalCase]:
    cases = []
    for path in sorted(cases_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.append(EvalCase.model_validate(raw))
    return cases
