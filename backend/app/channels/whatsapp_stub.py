"""WhatsApp channel — stubbed. The `ChannelAdapter` boundary (plan §11 / ADR
011) is what makes adding this later a transport concern, not a rewrite of
the engine.
"""
from __future__ import annotations

from app.channels.base import ChannelAdapter


class WhatsAppChannel(ChannelAdapter):
    def receive(self) -> str | None:
        raise NotImplementedError("WhatsApp channel is not implemented — see docs/04-decisions.md #011")

    def send(self, text: str) -> None:
        raise NotImplementedError("WhatsApp channel is not implemented — see docs/04-decisions.md #011")
