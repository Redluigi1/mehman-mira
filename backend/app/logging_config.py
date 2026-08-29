"""Structured logging — every record from the turn loop carries
`conversation_id` and `turn_index` (cross-cutting requirement, plan bottom).
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


class _ConversationFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        conversation_id = getattr(record, "conversation_id", "-")
        turn_index = getattr(record, "turn_index", "-")
        record.msg = f"[conversation_id={conversation_id} turn_index={turn_index}] {record.msg}"
        return super().format(record)


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ConversationFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _CONFIGURED = True


def turn_logger(name: str, conversation_id: str, turn_index: int) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger(name), {"conversation_id": conversation_id, "turn_index": turn_index})
