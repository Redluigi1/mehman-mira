"""find_alternatives — plan §3 tools table, §12 EC3/EC7. Called only when
`search_properties` came back with nothing at all, not even a near-miss
(`WIDEN_OR_ASK`). Tries a fixed sequence of wider relaxations, in an order
chosen to drop the least guest-stated intent first, and returns the first
one that produces results. If every relaxation still comes up empty, the
final pass — city, dates, party only — is the honest floor: whatever it
finds (or its absence) is the truthful answer to "is there really nothing?"
"""
from __future__ import annotations

from app.data.indexes import CityIndex
from app.data.repo import Repo
from app.tools.search import search_properties
from app.tools.types import SearchArgs, SearchResult


def find_alternatives(repo: Repo, city_index: CityIndex, args: SearchArgs) -> SearchResult:
    if args.budget_amount is not None:
        widened = args.model_copy(update={"budget_amount": None, "budget_basis": None})
        result = search_properties(repo, city_index, widened)
        if result.exact or result.near_miss:
            return result.model_copy(update={"strategy": "budget_ceiling_dropped"})

    if args.amenities_required:
        widened = args.model_copy(update={"amenities_required": []})
        result = search_properties(repo, city_index, widened)
        if result.exact or result.near_miss:
            return result.model_copy(update={"strategy": "amenities_dropped"})

    if args.property_types:
        widened = args.model_copy(update={"property_types": []})
        result = search_properties(repo, city_index, widened)
        if result.exact or result.near_miss:
            return result.model_copy(update={"strategy": "property_type_dropped"})

    floor = args.model_copy(update={
        "budget_amount": None, "budget_basis": None, "amenities_required": [],
        "property_types": [], "smoking": None, "pets": None,
        "bed_type": None, "view": None, "private_pool": None,
    })
    result = search_properties(repo, city_index, floor)
    strategy = "floor" if (result.exact or result.near_miss) else "none"
    return result.model_copy(update={"strategy": strategy})
