"""LLM backend selection."""
from __future__ import annotations

from app.llm.base import LLMClient
from app.llm.claude_cli import ClaudeCliClient
from app.llm.codex_cli import CodexCliClient
from app.llm.vertex import VertexAIClient


def build_llm_client(
    *,
    backend: str,
    model: str,
    timeout_s: float,
    reasoning_effort: str = "low",
    vertex_project: str | None = None,
    vertex_location: str = "global",
    vertex_api_key: str | None = None,
    vertex_credentials_file: str | None = None,
) -> LLMClient:
    if backend == "codex_cli":
        return CodexCliClient(
            model=model,
            timeout_s=timeout_s,
            reasoning_effort=reasoning_effort,
        )
    if backend == "claude_cli":
        return ClaudeCliClient(model=model, timeout_s=timeout_s)
    if backend in {"vertex", "vertex_ai"}:
        return VertexAIClient(
            model=model,
            project=vertex_project,
            location=vertex_location,
            api_key=vertex_api_key,
            credentials_file=vertex_credentials_file,
            timeout_s=timeout_s,
        )
    raise ValueError(f"unsupported LLM_BACKEND: {backend!r}")


__all__ = ["build_llm_client", "ClaudeCliClient", "CodexCliClient", "VertexAIClient"]
