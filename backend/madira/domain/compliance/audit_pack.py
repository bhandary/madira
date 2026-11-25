"""Audit pack: a date-bounded cellar report and a balanced journal CSV.

Purchases debit Inventory Asset and credit Accounts Payable. Variance and
shrinkage, and comps, breakage, and waste, credit Inventory Asset. Every
export is balanced to the cent. Retention comes from the organization and
defaults to seven years.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import DEFAULT_RETENTION_YEARS, record_audit_event, verify_audit_chain
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import as_qty, public_qty, valuation_cents
from madira.domain.procurement.pdf import render_text_pdf
from madira.models import (
    ConditionExcursion,
    CountSession,
    Document,
    Invoice,
    Organization,
    Product,
    ProductVariant,
    PurchaseOrder,
    Receipt,
    ReceiptLine,
    Sku,
    StockMovement,
    Supplier,
    User,
    Venue,
)
from madira.tenancy import current_request

ACTION_EXPORT = "compliance.audit_pack_exported"
RECEIVED_PO = frozenset({"part_received", "received", "closed"})
VARIANCE_TYPES = frozenset({"count_adjustment", "shrinkage"})
WASTE_TYPES = frozenset({"comp", "breakage", "waste"})
JOURNAL_COLUMNS = (
    "Date",
    "Reference",
    "Description",
    "Account",
    "Debit",
    "Credit",
    "Supplier",
    "Currency",
    "DocumentHash",
)


class Rejected(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def parse_day(value: str) -> date:
    text = (value or "").strip()
    try:
        day = date.fromisoformat(text)
    except ValueError as exc:
        raise Rejected("Dates must be YYYY-MM-DD.") from exc
    if day.isoformat() != text:
        raise Rejected("Dates must be YYYY-MM-DD.")
    return day


def _window(start: date, end: date) -> tuple[datetime, datetime]:
    if end < start:
        raise Rejected("end_date cannot be before start_date.")
    start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_at, end_at


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _in_window(value: datetime | None, start_at: datetime, end_at: datetime) -> bool:
    moment = _aware(value)
    if moment is None:
        return False
    return start_at <= moment < end_at


def _stamp(value: datetime | None) -> str | None:
    moment = _aware(value)
    if moment is None:
        return None
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(value: datetime | None) -> str:
    moment = _aware(value)
    if moment is None:
        return ""
    return moment.date().isoformat()


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _money(cents: int) -> str:
    sign = "-" if int(cents) < 0 else ""
    amount = abs(int(cents))
    return f"{sign}${amount // 100:,}.{amount % 100:02d}"


def _dollars(cents: int) -> str:
    amount = abs(int(cents))
    return f"{amount // 100}.{amount % 100:02d}"


def _cents(text: str) -> int:
    body = (text or "").strip()
    if not body:
        return 0
    negative = body.startswith("-")
    if negative:
        body = body[1:]
    whole, frac = body.split(".")
    cents = int(whole) * 100 + int(frac)
    return -cents if negative else cents


def _actor(actor) -> tuple[uuid.UUID | None, str]:
    user_id = getattr(actor, "user_id", None) if actor is not None else None
    email = getattr(actor, "email", None) if actor is not None else None
    if user_id is None or not email:
        ctx = current_request()
        if ctx is not None:
            if user_id is None:
                user_id = ctx.user_id
            if not email:
                email = ctx.email
    return user_id, email or ""


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def chain_public(chain: dict) -> dict:
    checked = int(chain.get("checked_count") or 0)
    return {
        "valid": bool(chain.get("valid")),
        "checked": checked,
        "checked_count": checked,
        "head_hash": chain.get("head_hash"),
        "broken_event_id": chain.get("broken_event_id"),
        "reason": chain.get("reason"),
    }


def _sku_names(session: Session, venue_id: uuid.UUID) -> dict[uuid.UUID, tuple[str, str, int]]:
    rows = session.execute(
        select(Sku, Product.name)
        .join(ProductVariant, ProductVariant.id == Sku.product_variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Sku.venue_id == venue_id)
    ).all()
    found: dict[uuid.UUID, tuple[str, str, int]] = {}
    for stock, name in rows:
        found[stock.id] = (stock.barcode or str(stock.id), name or "", int(stock.cost or 0))
    return found


def _cost(movement: StockMovement, names: dict) -> int:
    if movement.unit_cost_cents is not None:
        return int(movement.unit_cost_cents)
    coded = names.get(movement.sku_id)
    return 0 if coded is None else coded[2]


def _sku_code(movement: StockMovement, names: dict) -> tuple[str, str]:
    coded = names.get(movement.sku_id)
    if coded is None:
        return str(movement.sku_id), ""
    return coded[0], coded[1]


def _valuation(session: Session, venue_id: uuid.UUID, start_at: datetime, end_at: datetime) -> dict:
    names = _sku_names(session, venue_id)
    movements = session.scalars(
        select(StockMovement).where(StockMovement.venue_id == venue_id).order_by(StockMovement.created_at, StockMovement.id)
    ).all()
    start_qty: dict[uuid.UUID, Decimal] = {}
    end_qty: dict[uuid.UUID, Decimal] = {}
    for row in movements:
        moment = _aware(row.created_at)
        if moment is None:
            continue
        qty = as_qty(row.quantity)
        if moment < start_at:
            start_qty[row.sku_id] = start_qty.get(row.sku_id, Decimal("0")) + qty
        if moment < end_at:
            end_qty[row.sku_id] = end_qty.get(row.sku_id, Decimal("0")) + qty
    sku_ids = set(names) | set(start_qty) | set(end_qty)
    lines = []
    start_bottles = Decimal("0")
    end_bottles = Decimal("0")
    start_value = 0
    end_value = 0
    for sku_id in sku_ids:
        code, product_name, unit_cost = names.get(sku_id, (str(sku_id), "", 0))
        opening = start_qty.get(sku_id, Decimal("0"))
        closing = end_qty.get(sku_id, Decimal("0"))
        opening_cents = valuation_cents(opening, unit_cost)
        closing_cents = valuation_cents(closing, unit_cost)
        start_bottles += opening
        end_bottles += closing
        start_value += opening_cents
        end_value += closing_cents
        if opening == 0 and closing == 0:
            continue
        lines.append(
            {
                "sku": code,
                "product_name": product_name,
                "unit_cost_cents": unit_cost,
                "start_bottles": public_qty(opening),
                "start_value_cents": opening_cents,
                "end_bottles": public_qty(closing),
                "end_value_cents": closing_cents,
            }
        )
    lines.sort(key=lambda row: (row["sku"], row["product_name"]))
    return {
        "start_bottles": public_qty(start_bottles),
        "start_value_cents": start_value,
        "end_bottles": public_qty(end_bottles),
        "end_value_cents": end_value,
        "skus": lines,
    }


def _linked_po_ids(session: Session, venue_id: uuid.UUID) -> set[uuid.UUID]:
    linked: set[uuid.UUID] = set()
    invoices = session.scalars(
        select(Invoice.purchase_order_id).where(
            Invoice.venue_id == venue_id,
            Invoice.purchase_order_id.is_not(None),
        )
    ).all()
    linked.update(row for row in invoices if row is not None)
    receipts = session.scalars(
        select(Receipt).where(Receipt.venue_id == venue_id, Receipt.invoice_id.is_not(None))
    ).all()
    linked.update(row.purchase_order_id for row in receipts)
    return linked


def missing_invoice_gaps(
    session: Session,
    venue_id: uuid.UUID,
    start: date | None,
    end: date | None,
) -> list[dict]:
    """Received purchase orders, and accepted receipts, with no vaulted invoice."""

    start_at = end_at = None
    if start is not None or end is not None:
        if start is None or end is None:
            raise Rejected("start_date and end_date are both required.")
        start_at, end_at = _window(start, end)
    linked = _linked_po_ids(session, venue_id)
    orders = session.scalars(select(PurchaseOrder).where(PurchaseOrder.venue_id == venue_id)).all()
    by_id = {row.id: row for row in orders}
    receipts = session.scalars(select(Receipt).where(Receipt.venue_id == venue_id)).all()
    receipts_by_po: dict[uuid.UUID, list[Receipt]] = {}
    for receipt in receipts:
        receipts_by_po.setdefault(receipt.purchase_order_id, []).append(receipt)
    candidates: set[uuid.UUID] = set()
    for order in orders:
        if order.status in RECEIVED_PO:
            candidates.add(order.id)
    for receipt in receipts:
        if receipt.status == "accepted" and receipt.invoice_id is None:
            candidates.add(receipt.purchase_order_id)
    gaps = []
    for po_id in candidates:
        if po_id in linked:
            continue
        order = by_id.get(po_id)
        if order is None:
            continue
        if start_at is not None and end_at is not None:
            touched = _in_window(order.created_at, start_at, end_at) or _in_window(
                order.updated_at, start_at, end_at
            ) or _in_window(order.sent_at, start_at, end_at)
            if not touched:
                touched = any(
                    _in_window(row.accepted_at or row.created_at, start_at, end_at)
                    for row in receipts_by_po.get(po_id, [])
                )
            if not touched:
                continue
        supplier = session.get(Supplier, order.supplier_id)
        gaps.append(
            {
                "purchase_order_id": str(order.id),
                "po_number": order.po_number or "",
                "supplier": "" if supplier is None else supplier.name,
                "status": order.status,
                "reason": "No vaulted invoice is linked to this received purchase order.",
            }
        )
    gaps.sort(key=lambda row: (row["po_number"], row["purchase_order_id"]))
    return gaps


def _purchases(session: Session, venue_id: uuid.UUID, start: date, end: date, start_at: datetime, end_at: datetime) -> tuple[list[dict], list[dict]]:
    suppliers = {row.id: row for row in session.scalars(select(Supplier).where(Supplier.venue_id == venue_id)).all()}
    orders = session.scalars(select(PurchaseOrder).where(PurchaseOrder.venue_id == venue_id)).all()
    invoices = session.scalars(select(Invoice).where(Invoice.venue_id == venue_id)).all()
    documents = {
        row.id: row
        for row in session.scalars(select(Document).where(Document.venue_id == venue_id)).all()
    }
    receipts = session.scalars(select(Receipt).where(Receipt.venue_id == venue_id)).all()
    receipt_ids = [row.id for row in receipts if row.status == "accepted" and _in_window(row.accepted_at or row.created_at, start_at, end_at)]
    lines = []
    if receipt_ids:
        lines = session.scalars(select(ReceiptLine).where(ReceiptLine.receipt_id.in_(receipt_ids))).all()
    line_value: dict[uuid.UUID, int] = {}
    for line in lines:
        unit = line.invoiced_unit_cost_cents if line.invoiced_unit_cost_cents is not None else int(line.ordered_unit_cost_cents or 0)
        line_value[line.receipt_id] = line_value.get(line.receipt_id, 0) + valuation_cents(line.counted_qty or 0, unit)
    received_by_supplier: dict[uuid.UUID, int] = {}
    receipt_supplier: dict[uuid.UUID, uuid.UUID] = {}
    for receipt in receipts:
        order = next((row for row in orders if row.id == receipt.purchase_order_id), None)
        if order is None:
            continue
        receipt_supplier[receipt.id] = order.supplier_id
        if receipt.id in line_value:
            received_by_supplier[order.supplier_id] = received_by_supplier.get(order.supplier_id, 0) + line_value[receipt.id]

    def invoice_in_window(row: Invoice) -> bool:
        text = (row.invoice_date or "").strip()
        return start.isoformat() <= text <= end.isoformat()

    window_invoices = [row for row in invoices if invoice_in_window(row)]
    po_ids: dict[uuid.UUID, set[uuid.UUID]] = {}
    invoice_count: dict[uuid.UUID, int] = {}
    invoiced_cents: dict[uuid.UUID, int] = {}
    register = []
    orders_by_id = {row.id: row for row in orders}
    for row in window_invoices:
        invoice_count[row.supplier_id] = invoice_count.get(row.supplier_id, 0) + 1
        invoiced_cents[row.supplier_id] = invoiced_cents.get(row.supplier_id, 0) + int(row.total_cents or 0)
        if row.purchase_order_id is not None:
            po_ids.setdefault(row.supplier_id, set()).add(row.purchase_order_id)
        order = None if row.purchase_order_id is None else orders_by_id.get(row.purchase_order_id)
        document = documents.get(row.document_id)
        supplier = suppliers.get(row.supplier_id)
        register.append(
            {
                "invoice_number": row.invoice_number,
                "date": row.invoice_date,
                "supplier": "" if supplier is None else supplier.name,
                "po_number": "" if order is None else (order.po_number or ""),
                "total_cents": int(row.total_cents or 0),
                "status": row.status,
                "document_id": str(row.document_id),
                "download_path": f"/compliance/documents/{row.document_id}/download",
                "sha256": "" if document is None else document.sha256,
                "currency": row.currency or "USD",
            }
        )
    for order in orders:
        touched = _in_window(order.created_at, start_at, end_at) or _in_window(order.sent_at, start_at, end_at)
        if not touched:
            touched = any(
                receipt.purchase_order_id == order.id and _in_window(receipt.accepted_at or receipt.created_at, start_at, end_at)
                for receipt in receipts
            )
        if touched:
            po_ids.setdefault(order.supplier_id, set()).add(order.id)
    supplier_ids = set(po_ids) | set(invoice_count) | set(received_by_supplier)
    purchases = []
    for supplier_id in supplier_ids:
        supplier = suppliers.get(supplier_id)
        purchases.append(
            {
                "supplier": "" if supplier is None else supplier.name,
                "po_count": len(po_ids.get(supplier_id, set())),
                "invoice_count": invoice_count.get(supplier_id, 0),
                "total_invoiced_cents": invoiced_cents.get(supplier_id, 0),
                "total_received_value_cents": received_by_supplier.get(supplier_id, 0),
            }
        )
    purchases.sort(key=lambda row: row["supplier"])
    register.sort(key=lambda row: (row["date"], row["invoice_number"]))
    return purchases, register


def _movement_rows(session: Session, venue_id: uuid.UUID, start_at: datetime, end_at: datetime, kinds: frozenset[str]) -> list[dict]:
    names = _sku_names(session, venue_id)
    users = {row.id: row.email for row in session.scalars(select(User)).all()}
    rows = session.scalars(
        select(StockMovement)
        .where(StockMovement.venue_id == venue_id, StockMovement.movement_type.in_(tuple(kinds)))
        .order_by(StockMovement.created_at, StockMovement.id)
    ).all()
    found = []
    for row in rows:
        if not _in_window(row.created_at, start_at, end_at):
            continue
        code, product_name = _sku_code(row, names)
        unit = _cost(row, names)
        impact = valuation_cents(row.quantity, unit)
        actor = users.get(row.actor_user_id, "") if row.actor_user_id is not None else ""
        found.append(
            {
                "id": str(row.id),
                "occurred_at": _stamp(row.created_at),
                "sku": code,
                "product_name": product_name,
                "movement_type": row.movement_type,
                "quantity": public_qty(row.quantity),
                "quantity_delta": public_qty(row.quantity),
                "cost_impact_cents": impact,
                "actor": actor,
                "notes": row.reason or "",
            }
        )
    return found


def _variance(session: Session, venue_id: uuid.UUID, start_at: datetime, end_at: datetime) -> dict:
    sessions = session.scalars(select(CountSession).where(CountSession.venue_id == venue_id)).all()
    count_rows = []
    for row in sessions:
        moment = row.approved_at or row.submitted_at or row.started_at
        if not _in_window(moment, start_at, end_at):
            continue
        count_rows.append(
            {
                "id": str(row.id),
                "status": row.status,
                "occurred_at": _stamp(moment),
                "location_id": str(row.location_id),
                "notes": row.notes or "",
            }
        )
    movements = _movement_rows(session, venue_id, start_at, end_at, VARIANCE_TYPES)
    quantity = sum((as_qty(row["quantity"]) for row in movements), Decimal("0"))
    impact = sum(int(row["cost_impact_cents"]) for row in movements)
    return {
        "count_sessions": count_rows,
        "movements": movements,
        "quantity_delta": public_qty(quantity),
        "cost_impact_cents": impact,
    }


def _waste(session: Session, venue_id: uuid.UUID, start_at: datetime, end_at: datetime) -> dict:
    movements = _movement_rows(session, venue_id, start_at, end_at, WASTE_TYPES)
    impact = sum(int(row["cost_impact_cents"]) for row in movements)
    return {"movements": movements, "cost_impact_cents": impact}


def _retention(session: Session, venue: Venue, end: date) -> dict:
    org = session.get(Organization, venue.organization_id)
    years = DEFAULT_RETENTION_YEARS if org is None else int(org.document_retention_years or DEFAULT_RETENTION_YEARS)
    return {
        "document_retention_years": years,
        "retain_until": _add_years(end, years).isoformat(),
    }


def build_audit_pack(session: Session, venue_id: uuid.UUID, start_date: date, end_date: date, actor=None) -> dict:
    """Summarize one venue for the inclusive date window. This does not write."""

    _ = actor
    venue = _venue(session, venue_id)
    start_at, end_at = _window(start_date, end_date)
    purchases, register = _purchases(session, venue_id, start_date, end_date, start_at, end_at)
    return {
        "venue": {"id": str(venue.id), "name": venue.name},
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "purchases_by_supplier": purchases,
        "invoice_register": register,
        "missing_invoice_gaps": missing_invoice_gaps(session, venue_id, start_date, end_date),
        "inventory_valuation": _valuation(session, venue_id, start_at, end_at),
        "variance_and_shrinkage": _variance(session, venue_id, start_at, end_at),
        "comp_breakage_waste": _waste(session, venue_id, start_at, end_at),
        "retention": _retention(session, venue, end_date),
        "chain": chain_public(verify_audit_chain(session, venue_id)),
    }


def _certificate_gaps(session: Session, venue_id: uuid.UUID) -> list[dict]:
    from madira.domain.team.certificates import due_certificates

    return due_certificates(session, venue_id)


def _pos_gaps(session: Session, venue_id: uuid.UUID) -> list[dict]:
    from madira.domain.pos.service import gap_alerts

    return gap_alerts(session, venue_id)


def compliance_gaps(session: Session, venue_id: uuid.UUID) -> dict:
    _venue(session, venue_id)
    excursions = session.scalars(
        select(ConditionExcursion)
        .where(ConditionExcursion.venue_id == venue_id, ConditionExcursion.status == "open")
        .order_by(ConditionExcursion.created_at.desc(), ConditionExcursion.id.desc())
    ).all()
    return {
        "missing_invoice_gaps": missing_invoice_gaps(session, venue_id, None, None),
        "open_excursions": [
            {
                "id": str(row.id),
                "zone_id": str(row.zone_id),
                "reading_id": str(row.reading_id),
                "metric": row.metric,
                "measured_temp_c": float(row.measured_temp_c),
                "measured_humidity_pct": float(row.measured_humidity_pct),
                "affected_skus": list(row.affected_skus or []),
                "status": row.status,
                "created_at": _stamp(row.created_at),
            }
            for row in excursions
        ],
        "certificate_gaps": _certificate_gaps(session, venue_id),
        "pos_gaps": _pos_gaps(session, venue_id),
        "chain": chain_public(verify_audit_chain(session, venue_id)),
    }


def _csv(header: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _journal_rows(pack: dict) -> list[list[str]]:
    rows: list[list[str]] = []

    def pair(day: str, reference: str, description: str, debit: str, credit: str, cents: int, supplier: str, currency: str, digest: str) -> None:
        amount = abs(int(cents))
        if amount == 0:
            return
        money = _dollars(amount)
        rows.append([day, reference, description, debit, money, "", supplier, currency, digest])
        rows.append([day, reference, description, credit, "", money, supplier, currency, digest])

    for invoice in pack["invoice_register"]:
        total = int(invoice["total_cents"] or 0)
        number = invoice["invoice_number"]
        if total >= 0:
            pair(
                invoice["date"],
                number,
                f"Inventory purchase {number}",
                "Inventory Asset",
                "Accounts Payable",
                total,
                invoice["supplier"],
                invoice.get("currency") or "USD",
                invoice.get("sha256") or "",
            )
        else:
            pair(
                invoice["date"],
                number,
                f"Inventory purchase {number}",
                "Accounts Payable",
                "Inventory Asset",
                total,
                invoice["supplier"],
                invoice.get("currency") or "USD",
                invoice.get("sha256") or "",
            )
    for movement in pack["variance_and_shrinkage"]["movements"]:
        impact = int(movement["cost_impact_cents"])
        day = (movement["occurred_at"] or "")[:10]
        reference = f"VAR-{movement['id'][:8]}"
        description = f"{movement['movement_type']} {movement['sku']}"
        if impact < 0:
            pair(day, reference, description, "Inventory Shrinkage", "Inventory Asset", impact, "", "USD", "")
        elif impact > 0:
            pair(day, reference, description, "Inventory Asset", "Inventory Shrinkage", impact, "", "USD", "")
    for movement in pack["comp_breakage_waste"]["movements"]:
        impact = int(movement["cost_impact_cents"])
        day = (movement["occurred_at"] or "")[:10]
        reference = f"CBW-{movement['id'][:8]}"
        description = f"{movement['movement_type']} {movement['sku']}"
        if impact < 0:
            pair(day, reference, description, "Comps, Breakage & Waste", "Inventory Asset", impact, "", "USD", "")
        elif impact > 0:
            pair(day, reference, description, "Inventory Asset", "Comps, Breakage & Waste", impact, "", "USD", "")
    debit = sum(_cents(row[4]) for row in rows)
    credit = sum(_cents(row[5]) for row in rows)
    if debit != credit:
        raise Rejected("Journal entries do not balance.")
    return rows


def journal_csv(pack: dict) -> bytes:
    return _csv(list(JOURNAL_COLUMNS), _journal_rows(pack))


def summary_files(pack: dict) -> dict[str, bytes]:
    purchases = _csv(
        ["supplier", "po_count", "invoice_count", "total_invoiced_cents", "total_received_value_cents"],
        [
            [row["supplier"], row["po_count"], row["invoice_count"], row["total_invoiced_cents"], row["total_received_value_cents"]]
            for row in pack["purchases_by_supplier"]
        ],
    )
    invoices = _csv(
        ["invoice_number", "date", "supplier", "po_number", "total_cents", "status", "document_id", "download_path", "sha256"],
        [
            [
                row["invoice_number"],
                row["date"],
                row["supplier"],
                row["po_number"],
                row["total_cents"],
                row["status"],
                row["document_id"],
                row["download_path"],
                row["sha256"],
            ]
            for row in pack["invoice_register"]
        ],
    )
    valuation = pack["inventory_valuation"]
    valuation_csv = _csv(
        ["sku", "product_name", "unit_cost_cents", "start_bottles", "start_value_cents", "end_bottles", "end_value_cents"],
        [
            [
                row["sku"],
                row["product_name"],
                row["unit_cost_cents"],
                row["start_bottles"],
                row["start_value_cents"],
                row["end_bottles"],
                row["end_value_cents"],
            ]
            for row in valuation["skus"]
        ],
    )
    variance_rows = []
    for row in pack["variance_and_shrinkage"]["count_sessions"]:
        variance_rows.append(["count_session", row["id"], row["occurred_at"], "", "", "", "", row["notes"]])
    for row in pack["variance_and_shrinkage"]["movements"]:
        variance_rows.append(
            [
                "movement",
                row["id"],
                row["occurred_at"],
                row["sku"],
                row["movement_type"],
                row["quantity_delta"],
                row["cost_impact_cents"],
                row["notes"],
            ]
        )
    variance = _csv(
        ["kind", "id", "occurred_at", "sku", "movement_type", "quantity_delta", "cost_impact_cents", "notes"],
        variance_rows,
    )
    waste = _csv(
        ["occurred_at", "sku", "movement_type", "quantity", "cost_impact_cents", "actor", "notes"],
        [
            [row["occurred_at"], row["sku"], row["movement_type"], row["quantity"], row["cost_impact_cents"], row["actor"], row["notes"]]
            for row in pack["comp_breakage_waste"]["movements"]
        ],
    )
    return {
        "purchases_by_supplier.csv": purchases,
        "invoice_register.csv": invoices,
        "inventory_valuation.csv": valuation_csv,
        "variance_and_shrinkage.csv": variance,
        "comp_breakage_waste.csv": waste,
    }


def summary_csv(pack: dict) -> bytes:
    chunks = []
    for name, payload in summary_files(pack).items():
        chunks.append(name.encode("utf-8"))
        chunks.append(b"\n")
        chunks.append(payload)
        if not payload.endswith(b"\n"):
            chunks.append(b"\n")
        chunks.append(b"\n")
    return b"".join(chunks)


def summary_pdf(pack: dict) -> bytes:
    valuation = pack["inventory_valuation"]
    variance = pack["variance_and_shrinkage"]
    waste = pack["comp_breakage_waste"]
    retention = pack["retention"]
    chain = pack["chain"]
    years = retention["document_retention_years"]
    lines = [
        "Audit pack summary",
        f"Venue: {pack['venue']['name']}",
        f"Period: {pack['start_date']} to {pack['end_date']}",
        f"Retention: {years} years",
        f"Retain until: {retention['retain_until']}",
        f"Hash chain: {'verified' if chain['valid'] else 'not verified'}",
        f"Checked: {chain['checked']}",
        f"Head: {chain['head_hash'] or 'none'}",
        "",
        f"Valuation start: {valuation['start_bottles']} bottles, {_money(valuation['start_value_cents'])}",
        f"Valuation end: {valuation['end_bottles']} bottles, {_money(valuation['end_value_cents'])}",
        "",
        "Purchases by supplier",
    ]
    if not pack["purchases_by_supplier"]:
        lines.append("  none")
    for row in pack["purchases_by_supplier"][:12]:
        lines.append(
            f"  {row['supplier']}: {row['po_count']} POs, {row['invoice_count']} invoices, invoiced {_money(row['total_invoiced_cents'])}, received {_money(row['total_received_value_cents'])}"
        )
    lines.append("")
    lines.append(f"Invoice register: {len(pack['invoice_register'])}")
    for row in pack["invoice_register"][:12]:
        lines.append(f"  {row['invoice_number']} {row['date']} {row['supplier']} {_money(row['total_cents'])} {row['status']}")
    gaps = pack["missing_invoice_gaps"]
    lines.append(f"Missing invoices: {len(gaps)}")
    for row in gaps[:12]:
        lines.append(f"  {row['po_number'] or row['purchase_order_id']} {row['supplier']} {row['status']}")
    lines.append("")
    lines.append(
        f"Variance and shrinkage: {variance['quantity_delta']} bottles, cost {_money(variance['cost_impact_cents'])}"
    )
    lines.append(f"Count sessions: {len(variance['count_sessions'])}")
    lines.append(
        f"Comps, breakage and waste: cost {_money(waste['cost_impact_cents'])} across {len(waste['movements'])} movements"
    )
    return render_text_pdf(lines)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def zip_bundle(pack: dict) -> bytes:
    start = pack["start_date"]
    end = pack["end_date"]
    files = {
        "audit_pack_summary.pdf": summary_pdf(pack),
        "journal_entries.csv": journal_csv(pack),
        **summary_files(pack),
    }
    manifest = {
        "filename": f"madira-audit-pack-{start}-to-{end}.zip",
        "start_date": start,
        "end_date": end,
        "document_retention_years": pack["retention"]["document_retention_years"],
        "retain_until": pack["retention"]["retain_until"],
        "chain": {
            "valid": pack["chain"]["valid"],
            "checked": pack["chain"]["checked"],
            "head_hash": pack["chain"]["head_hash"],
        },
        "files": {name: {"sha256": _sha256(payload)} for name, payload in files.items()},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
    return buffer.getvalue()


def render_export(pack: dict, fmt: str) -> tuple[str, str, bytes]:
    kind = (fmt or "").strip().lower()
    start = pack["start_date"]
    end = pack["end_date"]
    if kind == "zip":
        return f"madira-audit-pack-{start}-to-{end}.zip", "application/zip", zip_bundle(pack)
    if kind == "journal_csv":
        return "journal_entries.csv", "text/csv", journal_csv(pack)
    if kind == "summary_pdf":
        return "audit_pack_summary.pdf", "application/pdf", summary_pdf(pack)
    if kind == "summary_csv":
        return "audit_pack_summaries.csv", "text/csv", summary_csv(pack)
    raise Rejected("format must be zip, journal_csv, summary_pdf, or summary_csv.")


def export_audit_pack(
    session: Session,
    venue_id: uuid.UUID,
    start_date: date,
    end_date: date,
    fmt: str,
    actor,
) -> tuple[str, str, bytes]:
    pack = build_audit_pack(session, venue_id, start_date, end_date, actor)
    filename, media, payload = render_export(pack, fmt)
    venue = _venue(session, venue_id)
    user_id, email = _actor(actor)
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue_id,
        action=ACTION_EXPORT,
        entity_type="audit_pack",
        entity_id=None,
        after={
            "format": (fmt or "").strip().lower(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "filename": filename,
            "document_retention_years": pack["retention"]["document_retention_years"],
        },
        actor_user_id=user_id,
        actor_email=email,
    )
    return filename, media, payload
