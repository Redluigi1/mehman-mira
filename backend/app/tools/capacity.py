"""Shared capacity math used by both search (estimating a listing) and
pricing (quoting a specific option) — kept in one place so the two never
silently disagree on how many rooms or extra beds a party needs.
"""
from __future__ import annotations

import math

from app.domain.supply import RoomType


def rooms_needed_for(total_guests: int, max_occupancy: int) -> int:
    if max_occupancy <= 0:
        return 1
    return max(1, math.ceil(total_guests / max_occupancy))


def extra_beds_needed(room: RoomType, total_guests: int, rooms_needed: int) -> int:
    if not room.extra_bed_allowed:
        return 0
    base_capacity = room.base_occupancy * rooms_needed
    if total_guests <= base_capacity:
        return 0
    max_extra_per_room = max(0, room.max_occupancy - room.base_occupancy)
    return min(total_guests - base_capacity, max_extra_per_room * rooms_needed)
