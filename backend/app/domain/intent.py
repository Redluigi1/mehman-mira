"""Guest-side domain model: what we understand about the guest's request.

Every extracted field is wrapped in `Slot[T]` so provenance survives the turn
it was set on — which turn, how confident the extractor was, whether it has
already been asked about (so the policy never re-asks), and whether the value
is an inference rather than something the guest actually said.
"""
from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Slot(BaseModel, Generic[T]):
    value: T | None = None
    confidence: float = 0.0
    source_turn: int | None = None
    asked_count: int = 0
    is_assumption: bool = False

    @property
    def is_set(self) -> bool:
        return self.value is not None


class PropertyType(str, Enum):
    HOTEL = "hotel"
    RESORT = "resort"
    VILLA = "villa"
    HOMESTAY = "homestay"
    GUESTHOUSE = "guesthouse"
    BOUTIQUE = "boutique"


class TripPurpose(str, Enum):
    LEISURE = "leisure"
    BUSINESS = "business"
    WORKATION = "workation"


class Occasion(str, Enum):
    ANNIVERSARY = "anniversary"
    BIRTHDAY = "birthday"
    HONEYMOON = "honeymoon"
    BACHELOR_BACHELORETTE = "bachelor_bachelorette"
    REUNION = "reunion"


class PartyType(str, Enum):
    """Derived, never asked directly — from party composition and explicit signals only."""

    SOLO = "solo"
    COUPLE = "couple"
    FAMILY_WITH_KIDS = "family_with_kids"
    FRIENDS_GROUP = "friends_group"
    EXTENDED_FAMILY = "extended_family"
    UNKNOWN = "unknown"


class BudgetBasis(str, Enum):
    PER_NIGHT = "per_night"
    TOTAL = "total"


class BedType(str, Enum):
    KING = "king"
    TWIN = "twin"
    QUEEN = "queen"
    BUNK = "bunk"


class ViewType(str, Enum):
    SEA = "sea"
    POOL = "pool"
    GARDEN = "garden"
    MOUNTAIN = "mountain"
    CITY = "city"
    NONE = "none"


class Destination(BaseModel):
    city: str
    area: str | None = None
    flexible: bool = False


class StayWindow(BaseModel):
    check_in: str | None = None  # ISO date, resolved deterministically from date_expression
    check_out: str | None = None
    nights: int | None = None
    flex_days: int = 0


class ChildAge(BaseModel):
    age: int


class Party(BaseModel):
    adults: int | None = None
    children: list[ChildAge] = Field(default_factory=list)
    rooms_needed: int | None = None

    @property
    def total_guests(self) -> int:
        return (self.adults or 0) + len(self.children)


class Budget(BaseModel):
    amount: float
    basis: BudgetBasis = BudgetBasis.PER_NIGHT
    hard: bool = False


class RoomPrefs(BaseModel):
    bed_type: BedType | None = None
    view: ViewType | None = None
    private_pool: bool | None = None
    connecting_rooms: bool | None = None


class PolicyNeeds(BaseModel):
    smoking: bool | None = None
    pets: bool | None = None
    early_checkin: bool | None = None
    late_checkout: bool | None = None
    party_friendly: bool | None = None


class GuestIntent(BaseModel):
    destination: Slot[Destination] = Field(default_factory=Slot)
    stay: Slot[StayWindow] = Field(default_factory=Slot)
    party: Slot[Party] = Field(default_factory=Slot)
    budget: Slot[Budget] = Field(default_factory=Slot)
    property_prefs: Slot[list[PropertyType]] = Field(default_factory=Slot)
    room_prefs: Slot[RoomPrefs] = Field(default_factory=Slot)
    amenities_required: Slot[list[str]] = Field(default_factory=Slot)
    amenities_nice: Slot[list[str]] = Field(default_factory=Slot)
    policy_needs: Slot[PolicyNeeds] = Field(default_factory=Slot)
    special_requirements: Slot[list[str]] = Field(default_factory=Slot)
    trip_purpose: Slot[TripPurpose] = Field(default_factory=Slot)
    occasion: Slot[Occasion] = Field(default_factory=Slot)

    # Derived, never asked directly, never spoken aloud (Decision 009).
    party_type: PartyType = PartyType.UNKNOWN

    def derive_party_type(self) -> PartyType:
        """Party composition plus explicitly stated signals only — never inferred age."""
        party = self.party.value
        occasion = self.occasion.value
        if party is None or party.adults is None:
            return PartyType.UNKNOWN
        if occasion in (Occasion.HONEYMOON, Occasion.ANNIVERSARY) and party.adults == 2 and not party.children:
            return PartyType.COUPLE
        if party.children:
            return PartyType.FAMILY_WITH_KIDS
        if party.adults == 1:
            return PartyType.SOLO
        if party.adults == 2:
            return PartyType.COUPLE
        if occasion == Occasion.BACHELOR_BACHELORETTE:
            return PartyType.FRIENDS_GROUP
        return PartyType.FRIENDS_GROUP

    def has_minimum_viable_search_set(self) -> bool:
        """destination + dates + party size — everything else is optional refinement."""
        return (
            self.destination.is_set
            and self.stay.is_set
            and self.stay.value is not None
            and self.stay.value.check_in is not None
            and self.stay.value.check_out is not None
            and self.party.is_set
            and self.party.value is not None
            and self.party.value.adults is not None
        )
