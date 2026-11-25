"""Read-only compliance queries. Filters are parameters, never SQL text.

Each result is an AuditTable: columns, typed rows, totals from this module,
and a link to the source record. Rows are capped and paged. The venue comes
from the caller.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import public_qty
from madira.domain.pos.service import gap_alerts
from madira.domain.reminders.service import LICENSE_LEAD_DAYS, open_reminders
from madira.domain.sensors.service import sensor_board
from madira.domain.session import session_scope
from madira.domain.team.certificates import REMINDER_DAYS, due_certificates, venue_today
from madira.models import (
    AuditEvent,
    BeverageList,
    Certificate,
    ConditionExcursion,
    Invoice,
    ListVersion,
    Product,
    ProductVariant,
    PurchaseOrder,
    Receipt,
    Sku,
    StockMovement,
    StorageZone,
    Supplier,
    Venue,
    VenueLicense,
)
from madira.timestamps import parse_stamp

PAGE_DEFAULT = 25
PAGE_MAX = 50


class QueryError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def answer_from_audit_table(table: dict) -> str:
    """Speak only the totals the table already computed."""

    totals = table.get("totals") if isinstance(table, dict) else None
    title = (table or {}).get("title") or "Audit"
    if not isinstance(totals, dict) or not totals:
        return f"{title}. The table has no totals."
    bits = [f"{key} {totals[key]}" for key in sorted(totals)]
    return f"{title}. Totals from the table: " + ", ".join(bits) + "."


def _page(limit: int, offset: int) -> tuple[int, int]:
    try:
        size = int(limit)
        start = int(offset)
    except (TypeError, ValueError):
        raise QueryError("Page size is not a number.") from None
    if isinstance(limit, bool) or isinstance(offset, bool) or size < 1 or size > PAGE_MAX or start < 0:
        raise QueryError("Page is out of range.")
    return size, start


def _when(value: str, *, end: bool) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = parse_stamp(text)
    except ValueError:
        raise QueryError("The date could not be read.") from None
    if end and len(text) == 10:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return parse_stamp(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _table(title: str, columns: list[dict], rows: list[dict], totals: dict, limit: int, offset: int) -> dict:
    return {
        "title": title,
        "columns": columns,
        "rows": rows[offset : offset + limit],
        "totals": totals,
        "page": {"limit": limit, "offset": offset, "total": len(rows)},
    }


def _link(label: str, href: str) -> dict:
    return {"label": label, "href": href}


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def stock_movements(
    venue_id: uuid.UUID,
    *,
    sku: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = PAGE_DEFAULT,
    offset: int = 0,
) -> dict:
    size, start = _page(limit, offset)
    start_at = _when(start_date, end=False)
    end_at = _when(end_date, end=True)
    code = (sku or "").strip().upper()
    with session_scope() as session:
        _venue(session, venue_id)
        filters = [StockMovement.venue_id == venue_id]
        if code:
            filters.append(func.upper(Sku.barcode) == code)
        if start_at is not None:
            filters.append(StockMovement.created_at >= start_at)
        if end_at is not None:
            filters.append(StockMovement.created_at <= end_at)
        joined = (
            select(StockMovement, Sku.barcode, Product.name)
            .join(Sku, Sku.id == StockMovement.sku_id)
            .join(ProductVariant, ProductVariant.id == Sku.product_variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(*filters)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        )
        found = session.execute(joined).all()
        sale = case((StockMovement.movement_type == "sale", func.abs(StockMovement.quantity)), else_=0)
        counted, net, depletion = session.execute(
            select(
                func.count(StockMovement.id),
                func.coalesce(func.sum(StockMovement.quantity), 0),
                func.coalesce(func.sum(sale), 0),
            )
            .select_from(StockMovement)
            .join(Sku, Sku.id == StockMovement.sku_id)
            .where(*filters)
        ).one()
        rows = []
        for movement, barcode, name in found:
            rows.append(
                {
                    "id": str(movement.id),
                    "cells": {
                        "sku": barcode,
                        "name": name,
                        "movement_type": movement.movement_type,
                        "quantity": public_qty(movement.quantity),
                        "when": _iso(movement.created_at),
                    },
                    "links": [_link("Inventory", f"/inventory?sku={barcode}")],
                }
            )
        table = _table(
            "Stock movements",
            [
                {"key": "sku", "label": "SKU", "type": "text"},
                {"key": "name", "label": "Name", "type": "text"},
                {"key": "movement_type", "label": "Type", "type": "text"},
                {"key": "quantity", "label": "Quantity", "type": "number"},
                {"key": "when", "label": "When", "type": "date"},
            ],
            rows,
            {
                "movement_count": int(counted or 0),
                "net": public_qty(net or 0),
                "depletion": public_qty(depletion or 0),
            },
            size,
            start,
        )
    return {"audit_table": table}


def conditions(venue_id: uuid.UUID, *, limit: int = PAGE_DEFAULT, offset: int = 0) -> dict:
    size, start = _page(limit, offset)
    with session_scope() as session:
        _venue(session, venue_id)
        excursions = session.execute(
            select(ConditionExcursion, StorageZone.name)
            .join(StorageZone, StorageZone.id == ConditionExcursion.zone_id)
            .where(ConditionExcursion.venue_id == venue_id)
            .order_by(ConditionExcursion.created_at.desc(), ConditionExcursion.id.desc())
        ).all()
        sensors = sensor_board(session, venue_id)
        rows = []
        for row, zone_name in excursions:
            rows.append(
                {
                    "id": f"excursion-{row.id}",
                    "cells": {
                        "kind": "excursion",
                        "subject": zone_name,
                        "detail": row.metric,
                        "when": _iso(row.created_at),
                    },
                    "links": [_link("Cellar", "/inventory")],
                }
            )
        gaps = 0
        for sensor in sensors:
            if not sensor.get("stale"):
                continue
            gaps += 1
            rows.append(
                {
                    "id": f"sensor-{sensor.get('id')}",
                    "cells": {
                        "kind": "sensor_gap",
                        "subject": sensor.get("name") or "",
                        "detail": sensor.get("external_id") or "",
                        "when": sensor.get("last_at") or "",
                    },
                    "links": [_link("Sensors", "/sensors")],
                }
            )
        table = _table(
            "Conditions",
            [
                {"key": "kind", "label": "Kind", "type": "text"},
                {"key": "subject", "label": "Subject", "type": "text"},
                {"key": "detail", "label": "Detail", "type": "text"},
                {"key": "when", "label": "When", "type": "date"},
            ],
            rows,
            {"excursion_count": len(excursions), "sensor_gap_count": gaps},
            size,
            start,
        )
    return {"audit_table": table}


def compliance_status(venue_id: uuid.UUID, *, limit: int = PAGE_DEFAULT, offset: int = 0) -> dict:
    size, start = _page(limit, offset)
    with session_scope() as session:
        _venue(session, venue_id)
        today = venue_today(session, venue_id)
        horizon = today + timedelta(days=REMINDER_DAYS)
        licenses = session.scalars(
            select(VenueLicense).where(VenueLicense.venue_id == venue_id).order_by(VenueLicense.expires_on.asc())
        ).all()
        certificates = session.scalars(
            select(Certificate).where(Certificate.venue_id == venue_id).order_by(Certificate.expires_on.asc())
        ).all()
        due_ids = {item["id"] for item in due_certificates(session, venue_id)}
        reminders = open_reminders(session, venue_id)
        rows = []
        for row in licenses:
            links = [_link("Records", "/records")]
            if row.document_id is not None:
                links.append(_link("Document", f"/records?document={row.document_id}"))
            window = "inside reminder window" if row.expires_on <= today + timedelta(days=LICENSE_LEAD_DAYS) else "recorded"
            rows.append(
                {
                    "id": f"license-{row.id}",
                    "cells": {
                        "kind": "license",
                        "label": row.label,
                        "status": window,
                        "due_on": row.expires_on.isoformat(),
                    },
                    "links": links,
                }
            )
        for row in certificates:
            links = [_link("Training", "/training")]
            if row.document_id is not None:
                links.append(_link("Document", f"/records?document={row.document_id}"))
            status = "due" if str(row.id) in due_ids or row.expires_on <= horizon else "current"
            rows.append(
                {
                    "id": f"certificate-{row.id}",
                    "cells": {
                        "kind": "certificate",
                        "label": row.label,
                        "status": status,
                        "due_on": row.expires_on.isoformat(),
                    },
                    "links": links,
                }
            )
        for item in reminders:
            rows.append(
                {
                    "id": f"reminder-{item['source_type']}-{item['source_id']}",
                    "cells": {
                        "kind": "reminder",
                        "label": item.get("title") or "",
                        "status": "open",
                        "due_on": item.get("due_on") or "",
                    },
                    "links": [_link("Tonight", "/")],
                }
            )
        table = _table(
            "Licenses and reminders",
            [
                {"key": "kind", "label": "Kind", "type": "text"},
                {"key": "label", "label": "Label", "type": "text"},
                {"key": "status", "label": "Status", "type": "text"},
                {"key": "due_on", "label": "Due", "type": "date"},
            ],
            rows,
            {
                "license_count": len(licenses),
                "certificate_count": len(certificates),
                "reminder_count": len(reminders),
            },
            size,
            start,
        )
    return {"audit_table": table}


def pos_gaps(venue_id: uuid.UUID, *, limit: int = PAGE_DEFAULT, offset: int = 0) -> dict:
    size, start = _page(limit, offset)
    with session_scope() as session:
        _venue(session, venue_id)
        alerts = gap_alerts(session, venue_id)
        rows = []
        unmapped = 0
        for index, alert in enumerate(alerts):
            if alert.get("kind") == "unmapped":
                unmapped += 1
            rows.append(
                {
                    "id": f"pos-{index}",
                    "cells": {"kind": alert.get("kind") or "", "title": alert.get("title") or ""},
                    "links": [_link("POS", alert.get("href") or "/pos")],
                }
            )
        table = _table(
            "POS gaps",
            [
                {"key": "kind", "label": "Kind", "type": "text"},
                {"key": "title", "label": "Title", "type": "text"},
            ],
            rows,
            {"gap_count": len(alerts), "unmapped_count": unmapped},
            size,
            start,
        )
    return {"audit_table": table}


def list_versions(venue_id: uuid.UUID, *, limit: int = PAGE_DEFAULT, offset: int = 0) -> dict:
    size, start = _page(limit, offset)
    with session_scope() as session:
        _venue(session, venue_id)
        found = session.execute(
            select(ListVersion, BeverageList.name)
            .join(BeverageList, BeverageList.id == ListVersion.list_id)
            .where(ListVersion.venue_id == venue_id)
            .order_by(ListVersion.created_at.desc(), ListVersion.id.desc())
        ).all()
        published = 0
        rows = []
        for version, name in found:
            links = [_link("List", "/list")]
            if version.public_token and version.public_revoked_at is None and version.status == "published":
                links.append(_link("Published list", f"/l/{version.public_token}"))
            if version.document_id is not None:
                links.append(_link("Document", f"/records?document={version.document_id}"))
            if version.status == "published":
                published += 1
            rows.append(
                {
                    "id": str(version.id),
                    "cells": {
                        "name": name,
                        "number": int(version.number),
                        "status": version.status,
                        "published_at": _iso(version.published_at),
                    },
                    "links": links,
                }
            )
        table = _table(
            "List versions",
            [
                {"key": "name", "label": "List", "type": "text"},
                {"key": "number", "label": "Number", "type": "number"},
                {"key": "status", "label": "Status", "type": "text"},
                {"key": "published_at", "label": "Published", "type": "date"},
            ],
            rows,
            {"version_count": len(found), "published_count": published},
            size,
            start,
        )
    return {"audit_table": table}


def purchases(venue_id: uuid.UUID, *, limit: int = PAGE_DEFAULT, offset: int = 0) -> dict:
    size, start = _page(limit, offset)
    with session_scope() as session:
        _venue(session, venue_id)
        orders = session.execute(
            select(PurchaseOrder, Supplier.name)
            .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .where(PurchaseOrder.venue_id == venue_id)
            .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
        ).all()
        receipts = session.scalars(
            select(Receipt).where(Receipt.venue_id == venue_id).order_by(Receipt.created_at.desc(), Receipt.id.desc())
        ).all()
        order_cents = int(
            session.scalar(
                select(func.coalesce(func.sum(PurchaseOrder.subtotal_cents), 0)).where(PurchaseOrder.venue_id == venue_id)
            )
            or 0
        )
        rows = []
        for order, supplier_name in orders:
            links = [_link("Purchasing", f"/purchasing?po={order.id}")]
            if order.pdf_document_id is not None:
                links.append(_link("PO PDF", f"/records?document={order.pdf_document_id}"))
            rows.append(
                {
                    "id": f"po-{order.id}",
                    "cells": {
                        "kind": "purchase_order",
                        "reference": order.po_number or supplier_name,
                        "status": order.status,
                        "amount_cents": int(order.subtotal_cents or 0),
                        "when": _iso(order.created_at),
                    },
                    "links": links,
                }
            )
        for receipt in receipts:
            links = [_link("Purchasing", f"/purchasing?po={receipt.purchase_order_id}")]
            if receipt.invoice_id is not None:
                invoice = session.get(Invoice, receipt.invoice_id)
                if invoice is not None and invoice.document_id is not None:
                    links.append(_link("Invoice", f"/records?document={invoice.document_id}"))
            rows.append(
                {
                    "id": f"receipt-{receipt.id}",
                    "cells": {
                        "kind": "receipt",
                        "reference": str(receipt.purchase_order_id),
                        "status": receipt.status,
                        "amount_cents": 0,
                        "when": _iso(receipt.received_at or receipt.created_at),
                    },
                    "links": links,
                }
            )
        table = _table(
            "Purchases and receipts",
            [
                {"key": "kind", "label": "Kind", "type": "text"},
                {"key": "reference", "label": "Reference", "type": "text"},
                {"key": "status", "label": "Status", "type": "text"},
                {"key": "amount_cents", "label": "Amount", "type": "money"},
                {"key": "when", "label": "When", "type": "date"},
            ],
            rows,
            {"order_count": len(orders), "receipt_count": len(receipts), "order_cents": order_cents},
            size,
            start,
        )
    return {"audit_table": table}


def audit_events(
    venue_id: uuid.UUID,
    *,
    action: str = "",
    actor: str = "",
    limit: int = PAGE_DEFAULT,
    offset: int = 0,
) -> dict:
    size, start = _page(limit, offset)
    kind = (action or "").strip()
    who = (actor or "").strip().casefold()
    if len(kind) > 80:
        raise QueryError("The action filter is too long.")
    with session_scope() as session:
        _venue(session, venue_id)
        stmt = select(AuditEvent).where(AuditEvent.venue_id == venue_id)
        if kind:
            stmt = stmt.where(AuditEvent.action == kind)
        if who:
            stmt = stmt.where(func.lower(AuditEvent.actor_email).contains(who))
        stmt = stmt.order_by(AuditEvent.seq.desc(), AuditEvent.id.desc())
        found = session.scalars(stmt).all()
        rows = []
        for event in found:
            rows.append(
                {
                    "id": str(event.id),
                    "cells": {
                        "seq": int(event.seq),
                        "actor": event.actor_email or "",
                        "action": event.action,
                        "entity": event.entity_type or "",
                        "when": _iso(event.created_at),
                    },
                    "links": [_link("Records", "/records")],
                }
            )
        table = _table(
            "Audit events",
            [
                {"key": "seq", "label": "Seq", "type": "number"},
                {"key": "actor", "label": "Actor", "type": "text"},
                {"key": "action", "label": "Action", "type": "text"},
                {"key": "entity", "label": "Entity", "type": "text"},
                {"key": "when", "label": "When", "type": "date"},
            ],
            rows,
            {"event_count": len(found)},
            size,
            start,
        )
    return {"audit_table": table}
