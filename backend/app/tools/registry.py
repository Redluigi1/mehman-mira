"""name -> (schema, callable), with JSON schema export and arg validation.
The single source of truth for "what tools exist" — used by `pipeline/act.py`
to dispatch, and available for introspection (docs, a future tool-list
endpoint) without hunting through each pipeline module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from pydantic import BaseModel

from app.data.indexes import CityIndex
from app.data.repo import Repo
from app.store.holds import HoldStore
from app.tools.addons import suggest_addons
from app.tools.alternatives import find_alternatives
from app.tools.availability import check_availability, get_room_details
from app.tools.booking import create_booking_hold
from app.tools.policy_tool import get_property_policies
from app.tools.pricing import calculate_quote
from app.tools.search import search_properties
from app.tools.types import (
    AvailabilityArgs, AvailabilityResult, BookingHoldArgs, BookingHoldResult,
    PropertyPoliciesArgs, PropertyPoliciesResult, QuoteArgs, QuoteResult,
    RoomDetailsArgs, RoomDetailsResult, SearchArgs, SearchResult,
    SuggestAddonsArgs, SuggestAddonsResult,
)


@dataclass
class ToolSpec:
    name: str
    description: str
    args_schema: type[BaseModel]
    result_schema: type[BaseModel] | None
    fn: Callable[[BaseModel], Any]

    def validate_args(self, raw_args: dict) -> BaseModel:
        return self.args_schema.model_validate(raw_args)

    def call(self, raw_args: dict) -> Any:
        return self.fn(self.validate_args(raw_args))


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def export_schemas(self) -> dict[str, dict]:
        return {
            name: {
                "description": spec.description,
                "args_schema": spec.args_schema.model_json_schema(),
                "result_schema": spec.result_schema.model_json_schema() if spec.result_schema else None,
            }
            for name, spec in self._tools.items()
        }


def build_default_registry(repo: Repo, city_index: CityIndex, hold_store: HoldStore, today: date) -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(ToolSpec(
        name="search_properties", description="Filter cascade over the catalogue; exact and near-miss buckets, ranked.",
        args_schema=SearchArgs, result_schema=SearchResult,
        fn=lambda args: search_properties(repo, city_index, args),
    ))
    registry.register(ToolSpec(
        name="check_availability", description="Units available for a room type over a date range.",
        args_schema=AvailabilityArgs, result_schema=AvailabilityResult,
        fn=lambda args: check_availability(repo, args),
    ))
    registry.register(ToolSpec(
        name="get_room_details", description="Full room record: capacity, bed config, amenities.",
        args_schema=RoomDetailsArgs, result_schema=RoomDetailsResult,
        fn=lambda args: get_room_details(repo, args),
    ))
    registry.register(ToolSpec(
        name="get_property_policies", description="Policy lookup with explicit known/not_applicable/unknown semantics.",
        args_schema=PropertyPoliciesArgs, result_schema=PropertyPoliciesResult,
        fn=lambda args: get_property_policies(repo, args),
    ))
    registry.register(ToolSpec(
        name="calculate_quote", description="Deterministic line-item price breakdown. The LLM never computes a number.",
        args_schema=QuoteArgs, result_schema=QuoteResult,
        fn=lambda args: calculate_quote(repo, args, today),
    ))
    registry.register(ToolSpec(
        name="create_booking_hold", description="Hold with TTL and idempotency key.",
        args_schema=BookingHoldArgs, result_schema=BookingHoldResult,
        fn=lambda args: create_booking_hold(hold_store, args),
    ))
    registry.register(ToolSpec(
        name="find_alternatives",
        description="Sequenced relaxation search used when nothing matches at all: drops budget, "
                     "then amenities, then property type, then returns the honest cheapest floor.",
        args_schema=SearchArgs, result_schema=SearchResult,
        fn=lambda args: find_alternatives(repo, city_index, args),
    ))
    registry.register(ToolSpec(
        name="suggest_addons",
        description="Eligibility-checked add-on suggestions, ranked by segment affinity, at most two with reasons.",
        args_schema=SuggestAddonsArgs, result_schema=SuggestAddonsResult,
        fn=lambda args: suggest_addons(repo, args),
    ))

    return registry
