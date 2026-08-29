"""Conversation-side domain model: everything that persists across turns."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.domain.intent import GuestIntent


class Stage(str, Enum):
    DISCOVER = "discover"
    SEARCH = "search"
    PRESENT = "present"
    NEGOTIATE = "negotiate"
    CONFIRM = "confirm"
    HELD = "held"


class RelaxationKind(str, Enum):
    DATE_SHIFT = "date_shift"
    OVER_BUDGET = "over_budget"
    CAPACITY_SPLIT = "capacity_split"
    POLICY_CONFLICT = "policy_conflict"
    MIN_STAY = "min_stay"


class Relaxation(BaseModel):
    kind: RelaxationKind
    detail: str


class OptionRef(BaseModel):
    """A search result the guest has been shown, addressable by ordinal ('the
    second one'). Self-contained with the facts as shown, so grounding never
    drifts from what the guest actually saw even if the catalogue changes
    between turns.
    """

    option_id: str
    property_id: str
    room_type_id: str
    ordinal: int  # 1-based, position as last presented
    property_name: str
    room_type_name: str
    city: str
    area: str | None = None
    star_tier: int
    rooms_needed: int
    nights: int
    price_per_night: float
    estimated_total: float
    relaxations: list[Relaxation] = Field(default_factory=list)


class ReferentRegistry(BaseModel):
    """Ordinal + id lookup for every option shown, so 'the second one' resolves."""

    options: list[OptionRef] = Field(default_factory=list)

    def by_ordinal(self, ordinal: int) -> OptionRef | None:
        return next((o for o in self.options if o.ordinal == ordinal), None)

    def by_id(self, option_id: str) -> OptionRef | None:
        return next((o for o in self.options if o.option_id == option_id), None)

    def replace(self, options: list[OptionRef]) -> "ReferentRegistry":
        return ReferentRegistry(options=options)


class RejectionReason(str, Enum):
    PRICE = "price"
    LOCATION = "location"
    CAPACITY = "capacity"
    AMENITIES = "amenities"
    POLICY = "policy"
    OTHER = "other"


class Rejection(BaseModel):
    option_id: str
    reason: RejectionReason
    turn_index: int


class ConflictKind(str, Enum):
    CAPACITY = "capacity"
    BUDGET = "budget"
    POLICY = "policy"
    MIN_STAY = "min_stay"
    PAST_DATE = "past_date"
    CONTRADICTION = "contradiction"


class Conflict(BaseModel):
    kind: ConflictKind
    detail: str
    field_paths: list[str] = Field(default_factory=list)
    resolved: bool = False


class UnknownFactResolution(str, Enum):
    ANSWERED_UNKNOWN = "answered_unknown"
    ESCALATED = "escalated"  # reserved for Phase 7 (Decision 011)


class UnknownFact(BaseModel):
    property_id: str
    question_key: str
    turn_index: int
    resolution_path: UnknownFactResolution = UnknownFactResolution.ANSWERED_UNKNOWN


class QuoteLineItem(BaseModel):
    label: str
    amount: float


class Quote(BaseModel):
    option_id: str
    nights: int
    room_subtotal: float
    line_items: list[QuoteLineItem]
    taxes: float
    fixed_fees: float
    total: float
    currency: str = "INR"


class BookingHold(BaseModel):
    hold_id: str
    option_id: str
    quote_total: float
    idempotency_key: str
    expires_at: str  # ISO datetime


class ConversationState(BaseModel):
    conversation_id: str
    turn_index: int = 0
    stage: Stage = Stage.DISCOVER
    intent: GuestIntent = Field(default_factory=GuestIntent)
    shortlist: list[OptionRef] = Field(default_factory=list)
    referents: ReferentRegistry = Field(default_factory=ReferentRegistry)
    focused_option: OptionRef | None = None
    quote: Quote | None = None
    hold: BookingHold | None = None
    upsell_offered_for_quote: str | None = None  # option_id — upsell timing rule (Bonus 1), never re-offered
    accepted_addon_ids: list[str] = Field(default_factory=list)  # deterministically matched from guest text against offered add-ons
    quote_addon_ids: list[str] = Field(default_factory=list)  # add-on ids baked into the current `quote` — detects when a rebuild is owed
    rejected: list[Rejection] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    unknowns_surfaced: list[UnknownFact] = Field(default_factory=list)
