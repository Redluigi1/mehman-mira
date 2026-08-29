"""check_availability and get_room_details — direct, typed lookups."""
from __future__ import annotations

from datetime import date

from app.data.indexes import AvailabilityIndex
from app.data.repo import Repo
from app.tools.types import (
    AvailabilityArgs, AvailabilityResult, RoomDetailsArgs, RoomDetailsResult,
)


def check_availability(repo: Repo, args: AvailabilityArgs) -> AvailabilityResult:
    check_in = date.fromisoformat(args.check_in)
    check_out = date.fromisoformat(args.check_out)
    nights = (check_out - check_in).days

    avail_index = AvailabilityIndex(repo, [args.room_type_id], check_in, check_out)
    units = avail_index.min_units_available(args.room_type_id, check_in, check_out)
    min_stay = max((r.min_stay for r in repo.get_rates(args.room_type_id, check_in, check_out)), default=1)

    return AvailabilityResult(
        room_type_id=args.room_type_id, check_in=args.check_in, check_out=args.check_out,
        units_available=units, is_available=units >= args.rooms_needed,
        min_stay=min_stay, meets_min_stay=nights >= min_stay,
    )


def get_room_details(repo: Repo, args: RoomDetailsArgs) -> RoomDetailsResult | None:
    room = repo.get_room_type(args.room_type_id)
    if room is None:
        return None
    prop = repo.get_property(room.property_id)
    if prop is None:
        return None
    return RoomDetailsResult(
        room_type_id=room.id, property_id=room.property_id, property_name=prop.name,
        name=room.name, base_occupancy=room.base_occupancy, max_occupancy=room.max_occupancy,
        max_adults=room.max_adults, max_children=room.max_children,
        extra_bed_allowed=room.extra_bed_allowed, extra_bed_price=room.extra_bed_price,
        bed_config=room.bed_config.value, size_sqft=room.size_sqft, view=room.view.value,
        amenities=room.amenities,
    )
