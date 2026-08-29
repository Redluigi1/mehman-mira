"""search_properties — filter cascade, exact and near-miss buckets, ranked.

Cascade (plan §4): city index -> availability -> capacity -> budget ceiling
-> required amenities -> policy compatibility -> score. Pruning is non-lossy
(Decision 008): a candidate becomes a near_miss with a typed Relaxation
inside a threshold, and is dropped only past it.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.data.indexes import AvailabilityIndex, CityIndex
from app.data.repo import Repo
from app.domain.state import Relaxation, RelaxationKind
from app.tools.capacity import extra_beds_needed, rooms_needed_for
from app.tools.types import SearchArgs, SearchHit, SearchResult

DATE_SHIFT_MAX_DAYS = 2
BUDGET_OVERSHOOT_MAX_PCT = 0.20
CAPACITY_SPLIT_MAX_ROOMS = 2

W_FIT = 0.35
W_PRICE = 0.25
W_SEG = 0.10
W_AMEN = 0.15
W_QUAL = 0.15
RELAXATION_PENALTY = 0.12


def _avg_nightly_rate(repo: Repo, room_type_id: str, check_in: date, check_out: date) -> float | None:
    rates = repo.get_rates(room_type_id, check_in, check_out)
    if not rates or len(rates) < (check_out - check_in).days:
        return None
    return sum(r.price for r in rates) / len(rates)


def _min_min_stay(repo: Repo, room_type_id: str, check_in: date, check_out: date) -> int:
    rates = repo.get_rates(room_type_id, check_in, check_out)
    return max((r.min_stay for r in rates), default=1)


def search_properties(repo: Repo, city_index: CityIndex, args: SearchArgs) -> SearchResult:
    check_in = date.fromisoformat(args.check_in)
    check_out = date.fromisoformat(args.check_out)
    nights = (check_out - check_in).days
    total_guests = args.adults + len(args.children_ages)

    property_ids = city_index.property_ids_for_city(args.city)
    if not property_ids:
        return SearchResult()

    all_room_type_ids = [rt.id for pid in property_ids for rt in repo.get_room_types(pid)]
    window_start = min(check_in, check_in - timedelta(days=DATE_SHIFT_MAX_DAYS))
    window_end = max(check_out, check_out + timedelta(days=DATE_SHIFT_MAX_DAYS))
    avail_index = AvailabilityIndex(repo, all_room_type_ids, window_start, window_end)

    exact: list[SearchHit] = []
    near_miss: list[SearchHit] = []

    for property_id in property_ids:
        prop = repo.get_property(property_id)
        if prop is None:
            continue
        if args.property_types and prop.type not in args.property_types:
            continue
        prop_amenities = set(prop.amenities)

        for room in repo.get_room_types(property_id):
            if args.amenities_required and not set(args.amenities_required) <= (prop_amenities | set(room.amenities)):
                continue

            rooms_needed = 1
            relaxations: list[Relaxation] = []

            if total_guests > room.max_occupancy:
                rooms_needed = rooms_needed_for(total_guests, room.max_occupancy)
                if rooms_needed > CAPACITY_SPLIT_MAX_ROOMS:
                    continue
                relaxations.append(Relaxation(
                    kind=RelaxationKind.CAPACITY_SPLIT,
                    detail=f"needs {rooms_needed} rooms of this type to fit {total_guests} guests",
                ))
            elif args.adults > room.max_adults or len(args.children_ages) > room.max_children:
                continue  # composition doesn't fit even with extra beds

            actual_check_in, actual_check_out = check_in, check_out
            if not avail_index.is_available(room.id, check_in, check_out, rooms_needed):
                shifted = _find_date_shift(avail_index, room.id, check_in, nights, rooms_needed)
                if shifted is None:
                    continue
                actual_check_in = shifted
                actual_check_out = shifted + timedelta(days=nights)
                relaxations.append(Relaxation(
                    kind=RelaxationKind.DATE_SHIFT,
                    detail=f"available from {actual_check_in.isoformat()} instead of {check_in.isoformat()}",
                ))

            min_stay = _min_min_stay(repo, room.id, actual_check_in, actual_check_out)
            if nights < min_stay:
                relaxations.append(Relaxation(
                    kind=RelaxationKind.MIN_STAY,
                    detail=f"requires a {min_stay}-night minimum stay",
                ))

            if args.smoking is True and repo.get_policy(property_id, "smoking").status == "known" \
                    and repo.get_policy(property_id, "smoking").value is False:
                relaxations.append(Relaxation(kind=RelaxationKind.POLICY_CONFLICT, detail="property is non-smoking"))
            if args.pets is True and repo.get_policy(property_id, "pets").status == "known" \
                    and repo.get_policy(property_id, "pets").value is False:
                relaxations.append(Relaxation(kind=RelaxationKind.POLICY_CONFLICT, detail="property does not allow pets"))

            avg_rate = _avg_nightly_rate(repo, room.id, actual_check_in, actual_check_out)
            if avg_rate is None:
                continue
            estimated_total = avg_rate * nights * rooms_needed
            extra_beds = extra_beds_needed(room, total_guests, rooms_needed)
            if extra_beds:
                estimated_total += (room.extra_bed_price or 0) * extra_beds * nights

            over_budget_pct = None
            if args.budget_amount is not None:
                budget_total = args.budget_amount * nights if args.budget_basis == "per_night" else args.budget_amount
                if estimated_total > budget_total:
                    over_budget_pct = (estimated_total - budget_total) / budget_total
                    if over_budget_pct > BUDGET_OVERSHOOT_MAX_PCT:
                        continue
                    relaxations.append(Relaxation(
                        kind=RelaxationKind.OVER_BUDGET,
                        detail=f"{over_budget_pct * 100:.0f}% over the stated budget",
                    ))

            score = _score(room, prop, args, avg_rate, over_budget_pct, relaxations)
            hit = SearchHit(
                option_id=f"{property_id}:{room.id}", property_id=property_id, property_name=prop.name,
                room_type_id=room.id, room_type_name=room.name, city=prop.city, area=prop.area,
                star_tier=prop.star_tier, rooms_needed=rooms_needed, nights=nights,
                price_per_night=round(avg_rate, 2), estimated_total=round(estimated_total, 2),
                relaxations=relaxations, score=score,
            )
            (near_miss if relaxations else exact).append(hit)

    exact.sort(key=lambda h: h.score, reverse=True)
    near_miss.sort(key=lambda h: h.score, reverse=True)
    return SearchResult(exact=exact, near_miss=near_miss)


def _find_date_shift(avail_index: AvailabilityIndex, room_type_id: str, check_in: date, nights: int, rooms_needed: int) -> date | None:
    for delta in range(1, DATE_SHIFT_MAX_DAYS + 1):
        for candidate in (check_in + timedelta(days=delta), check_in - timedelta(days=delta)):
            if avail_index.is_available(room_type_id, candidate, candidate + timedelta(days=nights), rooms_needed):
                return candidate
    return None


def _score(room, prop, args: SearchArgs, avg_rate: float, over_budget_pct: float | None, relaxations: list[Relaxation]) -> float:
    constraint_fit = 1.0 if room.max_adults >= args.adults and room.max_children >= len(args.children_ages) else 0.6

    if args.budget_amount is not None:
        price_fit = 1.0 if over_budget_pct is None else max(0.0, 1.0 - over_budget_pct)
    else:
        price_fit = 0.7

    segment_affinity = 0.5  # neutral by default; refined once party_type flows into scoring

    requested_amenities = set(args.amenities_required)
    room_amenities = set(room.amenities) | set(prop.amenities)
    amenity_overlap = 1.0 if not requested_amenities else len(requested_amenities & room_amenities) / len(requested_amenities)
    if args.bed_type is not None and room.bed_config == args.bed_type:
        amenity_overlap = min(1.0, amenity_overlap + 0.1)
    if args.view is not None and room.view == args.view:
        amenity_overlap = min(1.0, amenity_overlap + 0.1)

    quality = prop.star_tier / 5.0

    raw = (W_FIT * constraint_fit + W_PRICE * price_fit + W_SEG * segment_affinity
           + W_AMEN * amenity_overlap + W_QUAL * quality)
    return round(raw - RELAXATION_PENALTY * len(relaxations), 4)
