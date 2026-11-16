"""Reorder drafts. Line cost is unit cost times quantity, both from the stock rows."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from madira.domain.inventory.service import rows as inventory_rows
from madira.domain.session import session_scope
from madira.models import POLine, PurchaseOrder, Supplier
from madira.money import DEFAULT_CURRENCY


def draft(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        items = inventory_rows(session, venue_id)
        lows = [item for item in items if item["low"] and item["reorder_qty"] > 0]
        grouped: dict[uuid.UUID, list[dict]] = {}
        for item in lows:
            grouped.setdefault(item["supplier_id"], []).append(item)
        orders = []
        for supplier_id, lines in grouped.items():
            supplier = session.get(Supplier, supplier_id)
            if supplier is None or supplier.venue_id != venue_id:
                continue
            po = PurchaseOrder(
                venue_id=venue_id,
                supplier_id=supplier_id,
                status="draft",
                notes="Draft only — not transmitted to the supplier.",
            )
            session.add(po)
            session.flush()
            po_lines = []
            total = 0
            for line in lines:
                qty = line["reorder_qty"]
                unit_cost = int(line["unit_cost"])
                line_cost = unit_cost * qty
                session.add(
                    POLine(
                        venue_id=venue_id,
                        po_id=po.id,
                        sku=line["sku"],
                        name=line["name"],
                        qty=qty,
                        unit_cost=unit_cost,
                        currency=line.get("currency") or DEFAULT_CURRENCY,
                    )
                )
                po_lines.append({**line, "qty": qty, "unit_cost": unit_cost, "line_cost": line_cost})
                total += line_cost
            orders.append(
                {
                    "id": po.id,
                    "status": "draft",
                    "supplier": supplier.name if supplier else "",
                    "currency": DEFAULT_CURRENCY,
                    "total": total,
                    "lines": po_lines,
                    "notes": po.notes,
                }
            )
        session.commit()
        return {"orders": orders}


def list_orders(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        pos = session.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.venue_id == venue_id)
            .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
        ).all()
        return {
            "orders": [
                {
                    "id": po.id,
                    "status": po.status,
                    "supplier": po.supplier.name if po.supplier else "",
                    "notes": po.notes,
                    "lines": [
                        {
                            "sku": line.sku,
                            "name": line.name,
                            "qty": line.qty,
                            "unit_cost": line.unit_cost,
                            "currency": line.currency,
                        }
                        for line in po.lines
                    ],
                }
                for po in pos
            ]
        }
