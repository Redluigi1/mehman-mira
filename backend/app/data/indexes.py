"""In-memory indices built once at boot from the Repo. At 24 properties a
linear scan would do (Decision 008's honest note) — the point is the
interface: sorted per-room-type intervals with binary search, the shape that
survives a move to Postgres `daterange` + GiST.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from datetime import date

from app.data.repo import Repo


class CityIndex:
    def __init__(self, repo: Repo):
        self._by_city: dict[str, list[str]] = defaultdict(list)
        for p in repo.all_properties():
            self._by_city[p.city.lower()].append(p.id)

    def property_ids_for_city(self, city: str) -> list[str]:
        return list(self._by_city.get(city.lower(), []))


class AvailabilityIndex:
    """Sorted (date -> units_available) per room type, over the loaded window."""

    def __init__(self, repo: Repo, room_type_ids: list[str], start: date, end_exclusive: date):
        self._by_room: dict[str, tuple[list[str], list[int]]] = {}
        for rt_id in room_type_ids:
            entries = repo.get_inventory(rt_id, start, end_exclusive)
            self._by_room[rt_id] = ([e.date for e in entries], [e.units_available for e in entries])

    def min_units_available(self, room_type_id: str, checkin: date, checkout: date) -> int:
        """Minimum units free across every night of [checkin, checkout). Missing
        data for any night in range is treated as zero — we never claim
        availability we cannot confirm.
        """
        dates, units = self._by_room.get(room_type_id, ([], []))
        if not dates:
            return 0
        lo = bisect_left(dates, checkin.isoformat())
        hi = bisect_left(dates, checkout.isoformat())
        span = units[lo:hi]
        expected_nights = (checkout - checkin).days
        if expected_nights <= 0 or len(span) < expected_nights:
            return 0
        return min(span)

    def is_available(self, room_type_id: str, checkin: date, checkout: date, rooms_needed: int = 1) -> bool:
        return self.min_units_available(room_type_id, checkin, checkout) >= rooms_needed
