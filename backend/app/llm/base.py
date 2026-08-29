"""LLMClient protocol. Exactly two narrow calls per turn use this (Decision
001): schema-constrained state extraction, then response generation.
Everything else in the pipeline is deterministic Python.
"""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    def complete_json(self, *, system: str, user: str, schema: type[TModel]) -> TModel:
        """Return a validated instance of `schema`. Raises LLMError on failure."""
        ...

    def complete_text(self, *, system: str, user: str) -> str:
        """Return raw text. Raises LLMError on failure."""
        ...
