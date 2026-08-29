"""ChannelAdapter — the boundary between a transport (CLI, web, WhatsApp) and
the channel-agnostic `ConversationEngine`. Kept deliberately thin: a channel
only moves text in and out; all understanding happens in the engine.
"""
from __future__ import annotations

from typing import Protocol


class ChannelAdapter(Protocol):
    def receive(self) -> str | None:
        """Return the next guest message, or None when the channel is closed."""
        ...

    def send(self, text: str) -> None:
        """Deliver Mira's reply to the guest."""
        ...
