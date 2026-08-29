"""calculate_quote — fully deterministic pricing engine (Decision 004).
The LLM never produces a number; this returns the line-item breakdown the
response model may only quote back.

    per-night rate from RateCalendar (seasonal / weekend aware)
      + extra-bed charges for guests above base occupancy
      x nights, x rooms_needed
      = room subtotal
      - length-of-stay / early-bird discounts
      + add-ons (per_stay | per_night | per_person basis)
      + taxes (GST slab keyed off the average per-night tariff) + fixed fees
      = total
"""
from __future__ import annotations

from datetime import date

from app.data.repo import Repo
from app.tools.types import QuoteArgs, QuoteLineItemResult, QuoteResult

LOS_DISCOUNT_7_NIGHTS_PCT = 0.05
LOS_DISCOUNT_4_NIGHTS_PCT = 0.03
EARLY_BIRD_DAYS = 30
EARLY_BIRD_PCT = 0.05


def calculate_quote(repo: Repo, args: QuoteArgs, today: date) -> QuoteResult | None:
    room = repo.get_room_type(args.room_type_id)
    if room is None:
        return None
    check_in = date.fromisoformat(args.check_in)
    check_out = date.fromisoformat(args.check_out)
    nights = (check_out - check_in).days
    if nights <= 0:
        return None

    rates = repo.get_rates(args.room_type_id, check_in, check_out)
    if len(rates) < nights:
        return None  # incomplete rate data for the range — never guess a price

    room_nightly_total = sum(r.price for r in rates)
    room_subtotal = room_nightly_total * args.rooms_needed
    line_items: list[QuoteLineItemResult] = [
        QuoteLineItemResult(label=f"Room x {nights} night(s) x {args.rooms_needed} room(s)", amount=round(room_subtotal, 2)),
    ]

    if args.extra_beds > 0 and room.extra_bed_allowed and room.extra_bed_price:
        extra_bed_total = room.extra_bed_price * args.extra_beds * nights
        room_subtotal += extra_bed_total
        line_items.append(QuoteLineItemResult(label=f"Extra bed x {args.extra_beds}", amount=round(extra_bed_total, 2)))

    discount_total = 0.0
    if nights >= 7:
        discount = room_subtotal * LOS_DISCOUNT_7_NIGHTS_PCT
        discount_total += discount
        line_items.append(QuoteLineItemResult(label="Length-of-stay discount (7+ nights)", amount=-round(discount, 2)))
    elif nights >= 4:
        discount = room_subtotal * LOS_DISCOUNT_4_NIGHTS_PCT
        discount_total += discount
        line_items.append(QuoteLineItemResult(label="Length-of-stay discount (4+ nights)", amount=-round(discount, 2)))

    if (check_in - today).days >= EARLY_BIRD_DAYS:
        discount = room_subtotal * EARLY_BIRD_PCT
        discount_total += discount
        line_items.append(QuoteLineItemResult(label="Early-bird discount (30+ days out)", amount=-round(discount, 2)))

    addon_total = 0.0
    for addon_id in args.add_on_ids:
        addon = repo.get_addon(addon_id)
        if addon is None:
            continue
        if addon.price_basis == "per_stay":
            amount = addon.price
        elif addon.price_basis == "per_night":
            amount = addon.price * nights
        else:  # per_person
            amount = addon.price * args.guests_for_addons
        addon_total += amount
        line_items.append(QuoteLineItemResult(label=addon.name, amount=round(amount, 2)))

    taxable_amount = room_subtotal - discount_total
    avg_nightly_rate = room_nightly_total / nights
    tax_rule = repo.get_tax_rule()
    gst_percent = tax_rule.gst_percent_for(avg_nightly_rate)
    taxes = taxable_amount * gst_percent / 100
    fixed_fees = tax_rule.fixed_fee_per_stay
    total = taxable_amount + addon_total + taxes + fixed_fees

    return QuoteResult(
        option_id=args.option_id, nights=nights, rooms_needed=args.rooms_needed,
        room_subtotal=round(room_subtotal, 2), line_items=line_items,
        taxes=round(taxes, 2), fixed_fees=round(fixed_fees, 2), total=round(total, 2),
    )
