"""Record/replay fixtures for deterministic evals (plan §13). `record` mode
wraps a real LLMClient and caches every response by prompt hash; `replay`
mode serves only from the cache and never calls out, so the eval suite runs
with no credentials.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.llm.base import LLMClient, LLMError, TModel


def _prompt_key(system: str, user: str) -> str:
    digest = hashlib.sha256(f"{system}\n---\n{user}".encode("utf-8")).hexdigest()
    return digest[:20]


class ReplayClient(LLMClient):
    def __init__(self, fixtures_dir: Path, mode: Literal["record", "replay"] = "replay", inner: LLMClient | None = None):
        self.fixtures_dir = fixtures_dir
        self.mode = mode
        self.inner = inner
        if mode == "record" and inner is None:
            raise ValueError("record mode needs an inner LLMClient to call and cache")
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)

    def complete_json(self, *, system: str, user: str, schema: type[TModel]) -> TModel:
        key = _prompt_key(system, user)
        path = self.fixtures_dir / f"{key}.json"
        if self.mode == "record":
            result = self.inner.complete_json(system=system, user=user, schema=schema)
            path.write_text(json.dumps({
                "kind": "json", "system": system, "user": user, "response": result.model_dump(mode="json"),
            }, indent=2), encoding="utf-8")
            return result
        if not path.exists():
            raise LLMError(f"no recorded fixture for prompt hash {key} (system/user not seen in record mode)")
        cached = json.loads(path.read_text(encoding="utf-8"))
        return schema.model_validate(cached["response"])

    def complete_text(self, *, system: str, user: str) -> str:
        key = _prompt_key(system, user)
        path = self.fixtures_dir / f"{key}.json"
        if self.mode == "record":
            result = self.inner.complete_text(system=system, user=user)
            path.write_text(json.dumps({
                "kind": "text", "system": system, "user": user, "response": result,
            }, indent=2), encoding="utf-8")
            return result
        if not path.exists():
            raise LLMError(f"no recorded fixture for prompt hash {key} (system/user not seen in record mode)")
        cached = json.loads(path.read_text(encoding="utf-8"))
        return cached["response"]
