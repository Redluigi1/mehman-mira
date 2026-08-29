"""Deterministic prompt-injection guard (plan §12 EC8, Decision 001). The
extractor's system prompt already asks the model not to comply with embedded
instructions, but Decision 001's whole point is that reliability-critical
behaviour lives in deterministic code, not a polite request to the model.
This is a second, code-side check on the guest's raw text that runs whether
or not the extractor was fooled, and it decides the turn's `NextAction`
directly rather than trusting `user_act` classification for this case.
"""
from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    r"ignore (all|any|the)?\s*(previous|prior|above)\s*instructions",
    r"disregard (all|any|the)?\s*(previous|prior|above)",
    r"you are now\b",
    r"act as (a|an)\b",
    r"reveal (your|the) (system )?prompt",
    r"print (your|the) (system )?prompt",
    r"show (me )?(your|the) (system )?(prompt|instructions)",
    r"what (is|are) your (system )?instructions",
    r"forget (all|everything|your instructions)",
    r"new instructions\s*:",
    r"\bsystem prompt\b",
    r"\byou must (now )?obey\b",
    r"\bDAN\b",
    r"\bjailbreak\b",
    r"pretend (you are|to be)\b",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))
