"""Stage 5 — Ground. Compiles everything the turn learned into a
`GroundingPacket`: an allow-list of facts, and nothing else reaches the
response model (Decision 005). The validator in `respond.py` checks every
number and name in the draft against this packet.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.domain.state import ConversationState
from app.domain.trace import NextAction, NextActionType
from app.pipeline.policy import TurnContext


class GroundedOption(BaseModel):
    ordinal: int
    option_id: str
    property_name: str
    room_type_name: str
    city: str
    area: str | None
    star_tier: int
    rooms_needed: int
    nights: int
    price_per_night: float
    estimated_total: float
    relaxation_notes: list[str] = Field(default_factory=list)


class GroundedLineItem(BaseModel):
    label: str
    amount: float


class GroundedQuote(BaseModel):
    nights: int
    line_items: list[GroundedLineItem]
    taxes: float
    fixed_fees: float
    total: float
    currency: str


class GroundedHold(BaseModel):
    hold_id: str
    total: float
    currency: str
    expires_at: str


class GroundedFact(BaseModel):
    key: str
    status: str  # known | not_applicable | unknown
    value: bool | str | int | float | None = None


class GroundedConflict(BaseModel):
    kind: str
    detail: str


class GroundedAddon(BaseModel):
    id: str
    name: str
    price: float
    price_basis: str
    reason: str


class GroundingPacket(BaseModel):
    next_action: NextAction
    ask_field: str | None = None
    options: list[GroundedOption] = Field(default_factory=list)
    quote: GroundedQuote | None = None
    hold: GroundedHold | None = None
    facts: list[GroundedFact] = Field(default_factory=list)
    conflicts: list[GroundedConflict] = Field(default_factory=list)
    room_details: dict | None = None
    suggested_addons: list[GroundedAddon] = Field(default_factory=list)
    tool_errors: list[str] = Field(default_factory=list)

    allowed_numbers: list[str] = Field(default_factory=list)
    allowed_names: list[str] = Field(default_factory=list)


_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _collect_numbers(*values: float | int | None) -> set[str]:
    out: set[str] = set()
    for v in values:
        if v is None:
            continue
        out.add(str(int(v)) if float(v).is_integer() else f"{v:g}")
        out.add(f"{v:,.0f}")
        out.add(f"{v:,.2f}")
    return out


def _collect_numbers_from_text(text: str) -> set[str]:
    """Conflict details are free-text and may cite a figure (a budget ceiling,
    an estimated total) that appears nowhere else in the packet. Whatever
    number is already in the detail is, by construction, grounded — pull it
    out so the response validator doesn't flag Mira for repeating it.
    """
    out: set[str] = set()
    for token in _NUMBER_RE.findall(text):
        try:
            value = float(token.replace(",", ""))
        except ValueError:
            continue
        out |= _collect_numbers(value)
    return out


def build_grounding_packet(state: ConversationState, ctx: TurnContext, action: NextAction) -> GroundingPacket:
    packet = GroundingPacket(next_action=action, ask_field=action.ask_field)
    allowed_numbers: set[str] = set()
    allowed_names: set[str] = set()

    for c in state.conflicts:
        if c.resolved:
            continue
        packet.conflicts.append(GroundedConflict(kind=c.kind.value, detail=c.detail))
        allowed_numbers |= _collect_numbers_from_text(c.detail)

    for opt in state.shortlist:
        notes = [r.detail for r in opt.relaxations]
        packet.options.append(GroundedOption(
            ordinal=opt.ordinal, option_id=opt.option_id, property_name=opt.property_name,
            room_type_name=opt.room_type_name, city=opt.city, area=opt.area, star_tier=opt.star_tier,
            rooms_needed=opt.rooms_needed, nights=opt.nights, price_per_night=opt.price_per_night,
            estimated_total=opt.estimated_total, relaxation_notes=notes,
        ))
        allowed_names.add(opt.property_name)
        allowed_names.add(opt.room_type_name)
        allowed_numbers |= _collect_numbers(opt.price_per_night, opt.estimated_total, opt.nights, opt.star_tier, opt.rooms_needed)

    if state.quote is not None:
        q = state.quote
        packet.quote = GroundedQuote(
            nights=q.nights, line_items=[GroundedLineItem(label=li.label, amount=li.amount) for li in q.line_items],
            taxes=q.taxes, fixed_fees=q.fixed_fees, total=q.total, currency=q.currency,
        )
        allowed_numbers |= _collect_numbers(q.nights, q.taxes, q.fixed_fees, q.total, *[li.amount for li in q.line_items])

    if state.hold is not None:
        h = state.hold
        packet.hold = GroundedHold(hold_id=h.hold_id, total=h.quote_total, currency="INR", expires_at=h.expires_at)
        allowed_numbers |= _collect_numbers(h.quote_total)
        allowed_names.add(h.hold_id)

    if action.type == NextActionType.UPSELL and ctx.eligible_addons:
        for a in ctx.eligible_addons:
            packet.suggested_addons.append(GroundedAddon(id=a.id, name=a.name, price=a.price, price_basis=a.price_basis, reason=a.reason))
            allowed_names.add(a.name)
            allowed_numbers |= _collect_numbers(a.price)

    if ctx.last_policy_fact is not None:
        for pf in ctx.last_policy_fact.policies:
            packet.facts.append(GroundedFact(key=pf.key, status=pf.status, value=pf.value))
        allowed_names.add(ctx.last_policy_fact.property_name)

    if ctx.last_room_details is not None:
        rd = ctx.last_room_details
        packet.room_details = rd.model_dump(mode="json")
        allowed_names.add(rd.property_name)
        allowed_names.add(rd.name)
        allowed_numbers |= _collect_numbers(rd.base_occupancy, rd.max_occupancy, rd.max_adults, rd.max_children, rd.size_sqft)

    packet.allowed_numbers = sorted(allowed_numbers)
    packet.allowed_names = sorted(allowed_names)
    return packet
