"""Supply-side domain model: the catalogue. JSON is the source of truth
(Decision 007); SQLite is a build artifact loaded at boot.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.intent import BedType, PropertyType, ViewType


class PolicyStatus(str, Enum):
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class PolicyValue(BaseModel):
    """Load-bearing three-state value (Decision 005). Nothing is implicitly false."""

    status: PolicyStatus
    value: bool | str | int | float | None = None
    source: str | None = None

    @classmethod
    def known(cls, value: bool | str | int | float, source: str = "listed") -> "PolicyValue":
        return cls(status=PolicyStatus.KNOWN, value=value, source=source)

    @classmethod
    def not_applicable(cls) -> "PolicyValue":
        return cls(status=PolicyStatus.NOT_APPLICABLE)

    @classmethod
    def unknown(cls) -> "PolicyValue":
        return cls(status=PolicyStatus.UNKNOWN)


class GeoPoint(BaseModel):
    lat: float
    lng: float


class Property(BaseModel):
    id: str
    name: str
    city: str
    area: str | None = None
    geo: GeoPoint | None = None
    type: PropertyType
    star_tier: int = Field(ge=1, le=5)
    description: str
    amenities: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    check_in_time: str = "14:00"
    check_out_time: str = "11:00"


class RoomType(BaseModel):
    id: str
    property_id: str
    name: str
    base_occupancy: int
    max_occupancy: int
    max_adults: int
    max_children: int
    extra_bed_allowed: bool
    extra_bed_price: float | None = None
    bed_config: BedType
    size_sqft: int | None = None
    view: ViewType = ViewType.NONE
    amenities: list[str] = Field(default_factory=list)
    units_total: int


class RateEntry(BaseModel):
    room_type_id: str
    date: str  # ISO date
    price: float
    min_stay: int = 1
    closed_to_arrival: bool = False


class InventoryEntry(BaseModel):
    room_type_id: str
    date: str  # ISO date
    units_available: int


class Policy(BaseModel):
    property_id: str
    key: str  # e.g. "smoking", "pets", "pool_heated", "party_friendly"
    policy: PolicyValue


class AddOnScope(str, Enum):
    PROPERTY = "property"
    GLOBAL = "global"


class AddOnPriceBasis(str, Enum):
    PER_STAY = "per_stay"
    PER_NIGHT = "per_night"
    PER_PERSON = "per_person"


class AddOn(BaseModel):
    id: str
    scope: AddOnScope
    property_id: str | None = None  # set when scope == property
    category: str  # e.g. "transport", "food", "experience", "room_upgrade"
    name: str
    price: float
    price_basis: AddOnPriceBasis
    eligibility: str | None = None  # free-text rule, checked deterministically (e.g. "requires_airport")
    segment_affinity: list[str] = Field(default_factory=list)  # PartyType/TripPurpose/Occasion values


class TaxSlab(BaseModel):
    max_per_night_rate: float | None  # None = no upper bound
    gst_percent: float


class TaxRule(BaseModel):
    slabs: list[TaxSlab]
    fixed_fee_per_stay: float = 0.0

    def gst_percent_for(self, per_night_rate: float) -> float:
        for slab in self.slabs:
            if slab.max_per_night_rate is None or per_night_rate <= slab.max_per_night_rate:
                return slab.gst_percent
        return self.slabs[-1].gst_percent
