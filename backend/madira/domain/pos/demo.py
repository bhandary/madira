"""Deterministic sales for the demo venue. Live mode never uses this driver."""

from __future__ import annotations

from madira.domain.pos.adapter import CatalogVariation, PosLocation, SaleLine

MUSCADET_ITEM = "demo-item-muscadet"
MUSCADET_VARIATION = "demo-var-muscadet"
UNKNOWN_ITEM = "demo-item-unknown"
UNKNOWN_VARIATION = "demo-var-unknown"
DEMO_LOCATION = "demo-bar"


class DemoPosDriver:
    """One standing unmapped pour, plus the next Muscadet bottle after those already posted.

    The line ids are a function of the ledger. The same posted set returns the
    same lines, and a line id that is already in the ledger is not a new sale.
    """

    def __init__(self, posted_ids: set[str]) -> None:
        self._posted = set(posted_ids)

    def list_locations(self) -> list[PosLocation]:
        return [PosLocation(DEMO_LOCATION, "Main Bar")]

    def list_variations(self) -> list[CatalogVariation]:
        return [
            CatalogVariation(
                MUSCADET_ITEM,
                MUSCADET_VARIATION,
                "Muscadet Domaine de l'Ecu",
                "Bottle",
                "W-MUS-01",
            ),
            CatalogVariation(UNKNOWN_ITEM, UNKNOWN_VARIATION, "Unlisted pour", "Glass", ""),
        ]

    def search_sales(self, location_id: str, start_at: str, end_at: str) -> list[SaleLine]:
        del location_id, start_at
        n = 1
        while f"demo-order-{n}:line" in self._posted:
            n += 1
        lines = [
            SaleLine(
                order_id=f"demo-order-{i}",
                line_uid="line",
                item_id=MUSCADET_ITEM,
                variation_id=MUSCADET_VARIATION,
                name="Muscadet Domaine de l'Ecu",
                quantity="1",
                closed_at=end_at,
            )
            for i in range(1, n + 1)
        ]
        lines.append(
            SaleLine(
                order_id="demo-order-unknown",
                line_uid="line",
                item_id=UNKNOWN_ITEM,
                variation_id=UNKNOWN_VARIATION,
                name="Unlisted pour",
                quantity="1",
                closed_at=end_at,
            )
        )
        return lines
