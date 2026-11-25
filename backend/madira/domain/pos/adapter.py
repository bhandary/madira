"""The POS driver contract. Demo and Square both implement it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PosError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class PosLocation:
    location_id: str
    name: str


@dataclass(frozen=True)
class CatalogVariation:
    item_id: str
    variation_id: str
    name: str
    variation_name: str
    sku: str


@dataclass(frozen=True)
class SaleLine:
    order_id: str
    line_uid: str
    item_id: str
    variation_id: str
    name: str
    quantity: str
    closed_at: str

    @property
    def external_line_id(self) -> str:
        return f"{self.order_id}:{self.line_uid}"


class PosAdapter(Protocol):
    def list_locations(self) -> list[PosLocation]:
        """Locations this credential can sell from."""

    def list_variations(self) -> list[CatalogVariation]:
        """Catalog items and their variations."""

    def search_sales(self, location_id: str, start_at: str, end_at: str) -> list[SaleLine]:
        """Completed sale lines whose closed_at falls in the window, inclusive."""
