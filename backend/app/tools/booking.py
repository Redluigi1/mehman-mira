"""create_booking_hold — TTL plus idempotency key, so a repeated guest
confirmation ("yes", sent twice) never creates two holds.
"""
from __future__ import annotations

from app.store.holds import HoldStore
from app.tools.types import BookingHoldArgs, BookingHoldResult


def create_booking_hold(hold_store: HoldStore, args: BookingHoldArgs) -> BookingHoldResult:
    hold, reused = hold_store.create_or_reuse(args.option_id, args.quote_total, args.idempotency_key)
    return BookingHoldResult(
        hold_id=hold.hold_id, option_id=hold.option_id, quote_total=hold.quote_total,
        idempotency_key=hold.idempotency_key, expires_at=hold.expires_at.isoformat(), reused_existing=reused,
    )
