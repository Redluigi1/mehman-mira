"""Dev LLM backend: the local Claude Code CLI (Decision 003, open — must be
resolved before Phase 6 ships). Shells out to `claude -p ... --output-format
json`, restricted to no tools since these are narrow one-shot completions,
never an agent turn.
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMClient, LLMError, TModel


def _resolve_claude_binary() -> str:
    """On Windows, `claude` resolves to a `.cmd` shim that runs through
    cmd.exe — which mangles multi-line arguments (our prompts always are).
    Prefer the underlying claude.exe the shim wraps, when present.
    """
    found = shutil.which("claude")
    if not found:
        return "claude"
    if platform.system() == "Windows" and found.lower().endswith((".cmd", ".bat")):
        candidate = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if candidate.exists():
            return str(candidate)
    return found


_CLAUDE_BIN = _resolve_claude_binary()

_DISALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
    "NotebookEdit", "Agent", "ExitPlanMode", "Artifact",
]

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


class ClaudeCliClient(LLMClient):
    def __init__(self, model: str = "haiku", timeout_s: float = 30.0, max_retries: int = 1):
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    def complete_json(self, *, system: str, user: str, schema: type[TModel]) -> TModel:
        raw = self._run(system, user)
        text = _strip_fences(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"model did not return valid JSON: {e}\n---\n{text[:500]}") from e
        try:
            return schema.model_validate(data)
        except ValidationError as e:
            raise LLMError(f"model JSON did not match schema {schema.__name__}: {e}") from e

    def complete_text(self, *, system: str, user: str) -> str:
        return self._run(system, user)

    def _run(self, system: str, user: str) -> str:
        cmd = [
            _CLAUDE_BIN, "-p", user,
            "--model", self.model,
            "--output-format", "json",
            "--system-prompt", system,
            "--safe-mode",  # skip this repo's CLAUDE.md/skills/hooks — this is a narrow completion, not a coding session
            "--disallowed-tools", ",".join(_DISALLOWED_TOOLS),
            "--permission-mode", "bypassPermissions",
        ]
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_s, encoding="utf-8")
            except subprocess.TimeoutExpired as e:
                last_error = e
                continue
            if proc.returncode != 0:
                last_error = LLMError(f"claude CLI exited {proc.returncode}: {proc.stderr[:1000]}")
                continue
            try:
                envelope = json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                last_error = LLMError(f"claude CLI did not return a JSON envelope: {e}\n{proc.stdout[:500]}")
                continue
            if envelope.get("is_error"):
                last_error = LLMError(f"claude CLI reported an error: {envelope.get('result')}")
                continue
            return envelope["result"]
        raise LLMError(f"claude CLI failed after {self.max_retries + 1} attempt(s): {last_error}")
