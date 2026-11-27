"""Deterministic list selection.

Greedy fill, then a swap that keeps every cell already covered and adds one
that was open. Ties break on cost, then on the SKU id. A pick that would pass
the budget, the bottle capacity, or a section's budget share is skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from madira.domain.lists.coverage import Cell, style_match
from madira.domain.lists.pricing import SECTION_SHARES


@dataclass(frozen=True)
class Pick:
    sku_id: uuid.UUID
    product_id: uuid.UUID
    category: str
    style: str
    band: str
    name: str
    cost: int


def covers(pick: Pick, cell: Cell) -> bool:
    if pick.category != cell.category:
        return False
    if cell.band and pick.band != cell.band:
        return False
    return style_match(cell.style, pick.style)


def _share_for(category: str, shares: dict[str, int | None]) -> int | None:
    if category in shares:
        return shares[category]
    return SECTION_SHARES.get(category)


def _within(picks: list[Pick], budget: int, capacity: int | None, shares: dict[str, int | None]) -> bool:
    if sum(pick.cost for pick in picks) > int(budget):
        return False
    if capacity is not None and len(picks) > int(capacity):
        return False
    spent: dict[str, int] = {}
    for pick in picks:
        spent[pick.category] = spent.get(pick.category, 0) + pick.cost
    for category, amount in spent.items():
        share = _share_for(category, shares)
        if share is None:
            continue
        allocated = int(budget) * int(share) // 100
        if amount > allocated:
            return False
    return True


def _covered(picks: list[Pick], cells: list[Cell]) -> set[tuple[str, str, str]]:
    found = set()
    for cell in cells:
        if any(covers(pick, cell) for pick in picks):
            found.add(cell.key)
    return found


def choose(
    candidates: list[Pick],
    cells: list[Cell],
    budget: int,
    capacity: int | None,
    shares: dict[str, int | None] | None = None,
) -> tuple[list[Pick], list[Cell]]:
    """Return the chosen SKUs and the cells no chosen SKU fills."""

    limits = shares or {}
    pool = sorted(candidates, key=lambda pick: (pick.cost, str(pick.sku_id)))
    selected: list[Pick] = []
    open_cells = list(cells)
    guard = 0
    while open_cells and guard < len(pool) + 2:
        guard += 1
        best: tuple[tuple, Pick, list[Cell]] | None = None
        chosen_ids = {pick.sku_id for pick in selected}
        for pick in pool:
            if pick.sku_id in chosen_ids:
                continue
            gained = [cell for cell in open_cells if covers(pick, cell)]
            if not gained:
                continue
            trial = selected + [pick]
            if not _within(trial, budget, capacity, limits):
                continue
            key = (-len(gained), pick.cost, str(pick.sku_id))
            if best is None or key < best[0]:
                best = (key, pick, gained)
        if best is None:
            break
        pick = best[1]
        gained_keys = {cell.key for cell in best[2]}
        selected.append(pick)
        open_cells = [cell for cell in open_cells if cell.key not in gained_keys]

    improved = True
    swaps = 0
    while improved and swaps < len(cells) + 1:
        improved = False
        swaps += 1
        current = _covered(selected, cells)
        chosen_ids = {pick.sku_id for pick in selected}
        for cell in list(open_cells):
            incomers = [pick for pick in pool if covers(pick, cell) and pick.sku_id not in chosen_ids]
            incomers.sort(key=lambda pick: (pick.cost, str(pick.sku_id)))
            victims = sorted(selected, key=lambda pick: (str(pick.sku_id),))
            placed = False
            for incoming in incomers:
                for victim in victims:
                    trial = [pick for pick in selected if pick.sku_id != victim.sku_id]
                    trial.append(incoming)
                    if not _within(trial, budget, capacity, limits):
                        continue
                    covered = _covered(trial, cells)
                    if cell.key in covered and current <= covered and len(covered) > len(current):
                        selected = trial
                        open_cells = [item for item in cells if item.key not in covered]
                        improved = True
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break
    selected = sorted(selected, key=lambda pick: (pick.category, str(pick.sku_id)))
    return selected, open_cells
