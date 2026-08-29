"""Resolve a guest's reply to an add-on upsell offer against the add-ons
actually offered, the same referent-matching pattern as `referents.py`:
deterministic text matching against known entities, never an LLM guess.

Split on clause boundaries so "add the airport pickup, skip breakfast" reads
as two independent decisions instead of one negation clobbering both.
"""
from __future__ import annotations

import re

from app.tools.types import SuggestedAddon

_NEGATIONS = ("no ", "not ", "skip", "without", "don't", "dont", "never mind", "n/a")
_CLAUSE_SPLIT = re.compile(r"[,;]| but | and ")


def resolve_addon_response(
    text: str, eligible_addons: list[SuggestedAddon], previously_accepted: list[str],
) -> list[str]:
    accepted = set(previously_accepted)
    clauses = _CLAUSE_SPLIT.split(text.lower())
    for addon in eligible_addons:
        name = addon.name.lower()
        for clause in clauses:
            if name not in clause:
                continue
            if any(neg in clause for neg in _NEGATIONS):
                accepted.discard(addon.id)
            else:
                accepted.add(addon.id)
            break
    return [a.id for a in eligible_addons if a.id in accepted]
