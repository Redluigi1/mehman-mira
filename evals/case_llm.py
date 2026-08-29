"""Stands in for the two live LLM calls per turn (plan §13's "record" pass).
`complete_json` returns the case's hand-authored, schema-valid `StateDelta`
for the current turn — see `evals/README.md` for why extraction is scripted
rather than recorded from the real model. `complete_text` returns the case's
scripted reply, or raises to force the deterministic, always-grounded
template fallback (Decision 005) when the case leaves it unset.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))
sys.path.insert(0, str(_REPO_ROOT))

from app.llm.base import LLMClient, LLMError  # noqa: E402

from evals.case_schema import EvalCase  # noqa: E402


class CaseScriptedLLM(LLMClient):
    def __init__(self, case: EvalCase):
        self.case = case
        self._extract_i = 0
        self._text_i = 0

    def complete_json(self, *, system: str, user: str, schema):
        turn = self.case.turns[self._extract_i]
        self._extract_i += 1
        payload = turn.extracted_delta.model_dump()
        return schema.model_validate(payload)

    def complete_text(self, *, system: str, user: str) -> str:
        turn = self.case.turns[self._text_i]
        self._text_i += 1
        if turn.scripted_reply is None:
            raise LLMError("scripted case forces the deterministic template fallback")
        return turn.scripted_reply
