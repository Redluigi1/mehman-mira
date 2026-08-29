"""Query layer over the loaded SQLite DB — the interface that survives a
future move to Postgres. Deserializes rows into the Pydantic domain models
so nothing above this layer touches raw SQL.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from app.domain.supply import (
    AddOn, GeoPoint, InventoryEntry, Policy, PolicyValue, Property, RateEntry,
    RoomType, TaxRule,
)


class Repo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # -- properties -----------------------------------------------------

    def get_property(self, property_id: str) -> Property | None:
        row = self.conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
        return self._row_to_property(row) if row else None

    def list_properties_by_city(self, city: str) -> list[Property]:
        rows = self.conn.execute(
            "SELECT * FROM properties WHERE city = ? COLLATE NOCASE", (city,)
        ).fetchall()
        return [self._row_to_property(r) for r in rows]

    def all_properties(self) -> list[Property]:
        rows = self.conn.execute("SELECT * FROM properties").fetchall()
        return [self._row_to_property(r) for r in rows]

    def all_cities(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT city FROM properties").fetchall()
        return [r["city"] for r in rows]

    @staticmethod
    def _row_to_property(row: sqlite3.Row) -> Property:
        geo = None
        if row["lat"] is not None and row["lng"] is not None:
            geo = GeoPoint(lat=row["lat"], lng=row["lng"])
        return Property(
            id=row["id"], name=row["name"], city=row["city"], area=row["area"], geo=geo,
            type=row["type"], star_tier=row["star_tier"], description=row["description"],
            amenities=json.loads(row["amenities_json"]), images=json.loads(row["images_json"]),
            check_in_time=row["check_in_time"], check_out_time=row["check_out_time"],
        )

    # -- room types -------------------------------------------------------

    def get_room_types(self, property_id: str) -> list[RoomType]:
        rows = self.conn.execute("SELECT * FROM room_types WHERE property_id = ?", (property_id,)).fetchall()
        return [self._row_to_room_type(r) for r in rows]

    def get_room_type(self, room_type_id: str) -> RoomType | None:
        row = self.conn.execute("SELECT * FROM room_types WHERE id = ?", (room_type_id,)).fetchone()
        return self._row_to_room_type(row) if row else None

    @staticmethod
    def _row_to_room_type(row: sqlite3.Row) -> RoomType:
        return RoomType(
            id=row["id"], property_id=row["property_id"], name=row["name"],
            base_occupancy=row["base_occupancy"], max_occupancy=row["max_occupancy"],
            max_adults=row["max_adults"], max_children=row["max_children"],
            extra_bed_allowed=bool(row["extra_bed_allowed"]), extra_bed_price=row["extra_bed_price"],
            bed_config=row["bed_config"], size_sqft=row["size_sqft"], view=row["view"],
            amenities=json.loads(row["amenities_json"]), units_total=row["units_total"],
        )

    # -- policies ---------------------------------------------------------

    def get_policies(self, property_id: str) -> list[Policy]:
        rows = self.conn.execute("SELECT * FROM policies WHERE property_id = ?", (property_id,)).fetchall()
        return [self._row_to_policy(r) for r in rows]

    def get_policy(self, property_id: str, key: str) -> PolicyValue:
        row = self.conn.execute(
            "SELECT * FROM policies WHERE property_id = ? AND key = ?", (property_id, key)
        ).fetchone()
        if row is None:
            return PolicyValue.unknown()
        return self._row_to_policy(row).policy

    @staticmethod
    def _row_to_policy(row: sqlite3.Row) -> Policy:
        value = json.loads(row["value_json"]) if row["value_json"] is not None else None
        return Policy(
            property_id=row["property_id"], key=row["key"],
            policy=PolicyValue(status=row["status"], value=value, source=row["source"]),
        )

    # -- rates / inventory --------------------------------------------------

    def get_rates(self, room_type_id: str, start: date, end_exclusive: date) -> list[RateEntry]:
        rows = self.conn.execute(
            "SELECT * FROM rates WHERE room_type_id = ? AND date >= ? AND date < ? ORDER BY date",
            (room_type_id, start.isoformat(), end_exclusive.isoformat()),
        ).fetchall()
        return [
            RateEntry(room_type_id=r["room_type_id"], date=r["date"], price=r["price"],
                      min_stay=r["min_stay"], closed_to_arrival=bool(r["closed_to_arrival"]))
            for r in rows
        ]

    def get_inventory(self, room_type_id: str, start: date, end_exclusive: date) -> list[InventoryEntry]:
        rows = self.conn.execute(
            "SELECT * FROM inventory WHERE room_type_id = ? AND date >= ? AND date < ? ORDER BY date",
            (room_type_id, start.isoformat(), end_exclusive.isoformat()),
        ).fetchall()
        return [
            InventoryEntry(room_type_id=r["room_type_id"], date=r["date"], units_available=r["units_available"])
            for r in rows
        ]

    # -- addons -------------------------------------------------------------

    def get_addons(self, property_id: str | None = None) -> list[AddOn]:
        rows = self.conn.execute(
            "SELECT * FROM addons WHERE scope = 'global' OR property_id = ?", (property_id,)
        ).fetchall()
        return [
            AddOn(id=r["id"], scope=r["scope"], property_id=r["property_id"], category=r["category"],
                  name=r["name"], price=r["price"], price_basis=r["price_basis"],
                  eligibility=r["eligibility"], segment_affinity=json.loads(r["segment_affinity_json"]))
            for r in rows
        ]

    # -- meta -----------------------------------------------------------------

    def get_demo_today(self) -> date:
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'demo_today'").fetchone()
        return date.fromisoformat(row["value"])

    def get_tax_rule(self) -> TaxRule:
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'tax_rule_json'").fetchone()
        return TaxRule.model_validate(json.loads(row["value"]))
