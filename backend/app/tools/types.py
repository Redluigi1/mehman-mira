"""Shared argument/result models for tools. Each tool's schema is exported by
`tools/registry.py`; these are the typed shapes validated against it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.intent import BedType, PropertyType, ViewType
from app.domain.state import Relaxation


class SearchArgs(BaseModel):
    city: str
    check_in: str  # ISO date
    check_out: str  # ISO date
    adults: int
    children_ages: list[int] = Field(default_factory=list)
    budget_amount: float | None = None
    budget_basis: str | None = None  # per_night | total
    property_types: list[PropertyType] = Field(default_factory=list)
    amenities_required: list[str] = Field(default_factory=list)
    smoking: bool | None = None
    pets: bool | None = None
    bed_type: BedType | None = None
    view: ViewType | None = None
    private_pool: bool | None = None


class SearchHit(BaseModel):
    option_id: str
    property_id: str
    property_name: str
    room_type_id: str
    room_type_name: str
    city: str
    area: str | None
    star_tier: int
    rooms_needed: int
    nights: int
    price_per_night: float
    estimated_total: float
    relaxations: list[Relaxation] = Field(default_factory=list)
    score: float = 0.0


class SearchResult(BaseModel):
    exact: list[SearchHit] = Field(default_factory=list)
    near_miss: list[SearchHit] = Field(default_factory=list)
    strategy: str = ""  # set by find_alternatives to say which relaxation produced this result


class AvailabilityArgs(BaseModel):
    room_type_id: str
    check_in: str
    check_out: str
    rooms_needed: int = 1


class AvailabilityResult(BaseModel):
    room_type_id: str
    check_in: str
    check_out: str
    units_available: int
    is_available: bool
    min_stay: int
    meets_min_stay: bool


class RoomDetailsArgs(BaseModel):
    room_type_id: str


class RoomDetailsResult(BaseModel):
    room_type_id: str
    property_id: str
    property_name: str
    name: str
    base_occupancy: int
    max_occupancy: int
    max_adults: int
    max_children: int
    extra_bed_allowed: bool
    extra_bed_price: float | None
    bed_config: str
    size_sqft: int | None
    view: str
    amenities: list[str]


class PropertyPoliciesArgs(BaseModel):
    property_id: str
    keys: list[str] = Field(default_factory=list)  # empty = all known keys


class PolicyFact(BaseModel):
    key: str
    status: str  # known | not_applicable | unknown
    value: bool | str | int | float | None = None


class PropertyPoliciesResult(BaseModel):
    property_id: str
    property_name: str
    policies: list[PolicyFact]


class QuoteArgs(BaseModel):
    option_id: str
    property_id: str
    room_type_id: str
    check_in: str
    check_out: str
    rooms_needed: int = 1
    extra_beds: int = 0
    add_on_ids: list[str] = Field(default_factory=list)
    guests_for_addons: int = 1


class QuoteLineItemResult(BaseModel):
    label: str
    amount: float


class QuoteResult(BaseModel):
    option_id: str
    nights: int
    rooms_needed: int
    room_subtotal: float
    line_items: list[QuoteLineItemResult]
    taxes: float
    fixed_fees: float
    total: float
    currency: str = "INR"


class BookingHoldArgs(BaseModel):
    option_id: str
    quote_total: float
    idempotency_key: str


class BookingHoldResult(BaseModel):
    hold_id: str
    option_id: str
    quote_total: float
    idempotency_key: str
    expires_at: str
    reused_existing: bool = False


class SuggestAddonsArgs(BaseModel):
    property_id: str
    party_type: str | None = None
    trip_purpose: str | None = None
    occasion: str | None = None
    guests_for_addons: int = 1


class SuggestedAddon(BaseModel):
    id: str
    name: str
    price: float
    price_basis: str
    reason: str


class SuggestAddonsResult(BaseModel):
    property_id: str
    suggestions: list[SuggestedAddon] = Field(default_factory=list)
