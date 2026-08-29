"""In-memory booking hold store — TTL plus idempotency (plan §3 tools table)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

HOLD_TTL_MINUTES = 20


@dataclass
class HeldBooking:
    hold_id: str
    option_id: str
    quote_total: float
    idempotency_key: str
    expires_at: datetime


class HoldStore:
    def __init__(self) -> None:
        self._by_idempotency_key: dict[str, HeldBooking] = {}

    def create_or_reuse(self, option_id: str, quote_total: float, idempotency_key: str) -> tuple[HeldBooking, bool]:
        existing = self._by_idempotency_key.get(idempotency_key)
        now = datetime.now(timezone.utc)
        if existing is not None and existing.expires_at > now:
            return existing, True
        hold = HeldBooking(
            hold_id=f"hold-{uuid.uuid4().hex[:12]}", option_id=option_id, quote_total=quote_total,
            idempotency_key=idempotency_key, expires_at=now + timedelta(minutes=HOLD_TTL_MINUTES),
        )
        self._by_idempotency_key[idempotency_key] = hold
        return hold, False
