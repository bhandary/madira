"""Append-only stock ledger.

``post_movement`` is the only insert. It checks the venue, the sign of the
quantity, and then writes the movement, the cached ``inventory_items.on_hand``,
and a hash-chained audit event in one transaction. Nothing updates or deletes
a movement row. A count correction is a new ``count_adjustment``.

Depletion over the trailing 30 days:

* When the venue has an active POS connection, depletion is the sum of
  absolute ``sale`` quantities in the window. Those rows are the POS sales,
  including sales this sync posts with reason ``pos_sale``. Count adjustments
  and other shrinkage are not used, including for a SKU with no sale in the
  window.
* Otherwise, when the SKU has any ``sale`` movement in the window, depletion
  is the sum of the absolute sale quantities. Other movement types in the
  window are ignored so a transfer or a breakage does not double-count usage
  the till already recorded.
* When the window has no ``sale`` rows and the venue has no active POS
  connection, depletion is count-derived. It is the absolute value of the sum
  of negative ``count_adjustment`` quantities, plus other shrinkage outflows:
  ``breakage``, ``comp``, ``faulty_bottle``, and a negative ``return``.
  Transfers are excluded in both directions. A bottle that moved from the
  cellar to the bar is still in the venue.

Valuation is ``on_hand * unit_cost_cents`` using the SKU's current cost, not a
moving average of movement costs. Tenths are kept (``-0.5`` for an open
spirit) and money is rounded half up to the nearest cent.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import ACTION_INVENTORY, record_audit_event
from madira.domain.errors import NotFound
from madira.domain.inventory.qrcode import qr_svg
from madira.models import LOCATION_KINDS, MOVEMENT_TYPES, Bin, InventoryItem, Location, Product, ProductVariant, Sku, StockMovement, Venue
from madira.tenancy import current_request

ACTION_MOVEMENT = "inventory.movement"
ACTION_TRANSFER = "inventory.transfer"

_CENT = Decimal("0.01")
_DOLLAR = Decimal("1")
_MAX = Decimal("10000000000")
_POSITIVE = frozenset({"opening_balance", "receive", "transfer_in"})
_NEGATIVE = frozenset({"sale", "breakage", "comp", "faulty_bottle", "transfer_out"})
_SIGNED = frozenset({"count_adjustment", "return"})
_SHRINK = frozenset({"breakage", "comp", "faulty_bottle", "return"})
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")
_MAIN_CELLAR = "Main Cellar"


class Rejected(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def as_qty(value) -> Decimal:
    """Quantize a stock figure to hundredths. Tenths stay exact."""

    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, bool) or value is None:
        raise Rejected("quantity must be a number")
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, float):
        dec = Decimal(str(value))
    else:
        text = str(value).strip()
        if not text:
            raise Rejected("quantity must be a number")
        try:
            dec = Decimal(text)
        except Exception as exc:
            raise Rejected("quantity must be a number") from exc
    if not dec.is_finite():
        raise Rejected("quantity must be a number")
    quantized = dec.quantize(_CENT, rounding=ROUND_HALF_UP)
    if quantized.copy_abs() >= _MAX:
        raise Rejected("quantity is too large")
    return quantized


def public_qty(value) -> int | float:
    """Whole bottles stay integers. Open tenths stay one or two decimals."""

    qty = as_qty(value)
    if qty == qty.to_integral_value():
        return int(qty)
    return float(qty)


def valuation_cents(quantity, unit_cost_cents: int) -> int:
    amount = as_qty(quantity) * Decimal(int(unit_cost_cents))
    return int(amount.quantize(_DOLLAR, rounding=ROUND_HALF_UP))


def reorder_bottles(on_hand, par: int) -> int:
    short = Decimal(int(par)) - as_qty(on_hand)
    if short <= 0:
        return 0
    return int(short.to_integral_value(rounding=ROUND_CEILING))


def bin_payload(venue_id: uuid.UUID, code: str) -> str:
    return f"madira:bin:{venue_id}:{code}"


def _check_sign(movement_type: str, quantity: Decimal) -> str:
    kind = (movement_type or "").strip()
    if kind not in MOVEMENT_TYPES:
        raise Rejected("movement_type is not recognized")
    if quantity == 0:
        raise Rejected("quantity must be non-zero")
    if kind in _POSITIVE and quantity <= 0:
        raise Rejected(f"{kind} quantity must be positive")
    if kind in _NEGATIVE and quantity >= 0:
        raise Rejected(f"{kind} quantity must be negative")
    if kind not in _POSITIVE | _NEGATIVE | _SIGNED:
        raise Rejected("movement_type is not recognized")
    return kind


def _clip(value: str | None, limit: int, label: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > limit:
        raise Rejected(f"{label} is too long")
    return text


def _when(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _actor(venue_id: uuid.UUID, actor_user_id: uuid.UUID | None, actor_email: str | None):
    if actor_user_id is None and actor_email is None:
        ctx = current_request()
        if ctx is not None and ctx.venue_id == venue_id:
            return ctx.user_id, ctx.email or ""
    return actor_user_id, (actor_email or "")


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _sku_code(session: Session, venue_id: uuid.UUID, sku: str) -> Sku:
    code = (sku or "").strip().upper()
    if not code:
        raise NotFound(f"unknown sku {sku}")
    row = session.scalar(select(Sku).where(Sku.venue_id == venue_id, func.upper(Sku.barcode) == code))
    if row is None:
        raise NotFound(f"unknown sku {sku}")
    return row


def _location(session: Session, venue_id: uuid.UUID, location_id: uuid.UUID) -> Location:
    row = session.get(Location, location_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("location not found")
    return row


def _bin(session: Session, venue_id: uuid.UUID, bin_id: uuid.UUID, location_id: uuid.UUID) -> Bin:
    row = session.get(Bin, bin_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("bin not found")
    if row.location_id != location_id:
        raise Rejected("bin is not in that location")
    return row


def _items(session: Session, venue_id: uuid.UUID, sku_id: uuid.UUID) -> list[InventoryItem]:
    return list(
        session.scalars(
            select(InventoryItem).where(InventoryItem.venue_id == venue_id, InventoryItem.sku_id == sku_id)
        ).all()
    )


def _ensure_item(session: Session, venue_id: uuid.UUID, sku_id: uuid.UUID) -> InventoryItem:
    found = _items(session, venue_id, sku_id)
    if found:
        return found[0]
    row = InventoryItem(venue_id=venue_id, sku_id=sku_id, on_hand=Decimal("0"), unit="btl")
    session.add(row)
    session.flush()
    return row


def _sum(session: Session, venue_id: uuid.UUID, sku_id: uuid.UUID) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
            StockMovement.venue_id == venue_id,
            StockMovement.sku_id == sku_id,
        )
    )
    return as_qty(total or 0)


def _sync(session: Session, venue_id: uuid.UUID, sku_id: uuid.UUID) -> Decimal:
    total = _sum(session, venue_id, sku_id)
    for item in _items(session, venue_id, sku_id):
        item.on_hand = total
    session.flush()
    return total


def _lock(session: Session, venue_id: uuid.UUID, sku_id: uuid.UUID) -> None:
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    session.scalars(
        select(InventoryItem.id)
        .where(InventoryItem.venue_id == venue_id, InventoryItem.sku_id == sku_id)
        .with_for_update()
    ).all()


def movement_sum(session: Session, venue_id: uuid.UUID, sku_id: uuid.UUID) -> Decimal:
    return _sum(session, venue_id, sku_id)


def post_movement(
    session: Session,
    venue_id: uuid.UUID,
    *,
    sku: str,
    location_id: uuid.UUID,
    quantity,
    movement_type: str,
    bin_id: uuid.UUID | None = None,
    unit_cost_cents: int | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    reason: str | None = None,
    created_at: datetime | None = None,
    action: str = ACTION_MOVEMENT,
    entity_type: str = "stock_movement",
    entity_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
) -> StockMovement:
    """Insert one movement and refresh the on-hand cache. The caller commits."""

    venue = _venue(session, venue_id)
    stock = _sku_code(session, venue_id, sku)
    place = _location(session, venue_id, location_id)
    spot = _bin(session, venue_id, bin_id, place.id) if bin_id is not None else None
    qty = as_qty(quantity)
    kind = _check_sign(movement_type, qty)
    cost = None if unit_cost_cents is None else int(unit_cost_cents)
    if cost is not None and cost < 0:
        raise Rejected("unit_cost_cents cannot be negative")
    _ensure_item(session, venue_id, stock.id)
    _lock(session, venue_id, stock.id)
    previous = _sum(session, venue_id, stock.id)
    actor_id, email = _actor(venue_id, actor_user_id, actor_email)
    row = StockMovement(
        id=uuid.uuid4(),
        venue_id=venue_id,
        sku_id=stock.id,
        location_id=place.id,
        bin_id=None if spot is None else spot.id,
        quantity=qty,
        movement_type=kind,
        unit_cost_cents=cost,
        source_type=_clip(source_type, 80, "source_type"),
        source_id=_clip(source_id, 80, "source_id"),
        reason=_clip(reason, 2000, "reason"),
        actor_user_id=actor_id,
        created_at=_when(created_at),
    )
    session.add(row)
    session.flush()
    total = _sync(session, venue_id, stock.id)
    code = stock.barcode
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue_id,
        action=action,
        entity_type=entity_type,
        entity_id=row.id if entity_id is None else entity_id,
        before=before if before is not None else {"sku": code, "on_hand": public_qty(previous)},
        after=after
        if after is not None
        else {
            "sku": code,
            "on_hand": public_qty(total),
            "movement_type": kind,
            "quantity": public_qty(qty),
            "location_id": str(place.id),
        },
        actor_user_id=actor_id,
        actor_email=email,
    )
    return row


def transfer_stock(
    session: Session,
    venue_id: uuid.UUID,
    *,
    sku: str,
    from_location_id: uuid.UUID,
    to_location_id: uuid.UUID,
    quantity,
    from_bin_id: uuid.UUID | None = None,
    to_bin_id: uuid.UUID | None = None,
    reason: str | None = None,
    created_at: datetime | None = None,
) -> tuple[StockMovement, StockMovement]:
    """Post a paired out and in. The venue total does not change."""

    qty = as_qty(quantity)
    if qty <= 0:
        raise Rejected("transfer quantity must be positive")
    if from_location_id == to_location_id and from_bin_id == to_bin_id:
        raise Rejected("transfer needs two different locations or bins")
    shared = str(uuid.uuid4())
    note = reason
    outgoing = post_movement(
        session,
        venue_id,
        sku=sku,
        location_id=from_location_id,
        bin_id=from_bin_id,
        quantity=-qty,
        movement_type="transfer_out",
        source_type="transfer",
        source_id=shared,
        reason=note,
        created_at=created_at,
        action=ACTION_TRANSFER,
    )
    incoming = post_movement(
        session,
        venue_id,
        sku=sku,
        location_id=to_location_id,
        bin_id=to_bin_id,
        quantity=qty,
        movement_type="transfer_in",
        source_type="transfer",
        source_id=shared,
        reason=note,
        created_at=created_at,
        action=ACTION_TRANSFER,
    )
    return outgoing, incoming


def apply_count(session: Session, venue_id: uuid.UUID, sku: str, on_hand) -> None:
    """PATCH /inventory/{sku}: the delta from the movement sum is a count adjustment.

    A request that already matches the ledger still writes the inventory audit
    event, and it does not insert a zero-quantity row.
    """

    target = as_qty(on_hand)
    if target < 0:
        raise Rejected("on_hand cannot be negative")
    venue = _venue(session, venue_id)
    stock = _sku_code(session, venue_id, sku)
    items = _items(session, venue_id, stock.id)
    if not items:
        raise NotFound(f"unknown sku {sku}")
    _lock(session, venue_id, stock.id)
    total = _sum(session, venue_id, stock.id)
    previous = public_qty(total)
    desired = public_qty(target)
    code = stock.barcode
    delta = target - total
    if delta == 0:
        _sync(session, venue_id, stock.id)
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action=ACTION_INVENTORY,
            entity_type="inventory_item",
            entity_id=items[0].id,
            before={"sku": code, "on_hand": previous},
            after={"sku": code, "on_hand": desired},
        )
        return
    place = ensure_location(session, venue_id, _MAIN_CELLAR, "cellar")
    post_movement(
        session,
        venue_id,
        sku=sku,
        location_id=place.id,
        quantity=delta,
        movement_type="count_adjustment",
        source_type="count",
        reason="On-hand count",
        action=ACTION_INVENTORY,
        entity_type="inventory_item",
        entity_id=items[0].id,
        before={"sku": code, "on_hand": previous},
        after={"sku": code, "on_hand": desired},
    )


def ensure_location(session: Session, venue_id: uuid.UUID, name: str, kind: str, notes: str = "") -> Location:
    cleaned = _name(name)
    label = _kind(kind)
    existing = session.scalar(
        select(Location).where(Location.venue_id == venue_id, Location.name == cleaned)
    )
    if existing is not None:
        return existing
    _venue(session, venue_id)
    row = Location(venue_id=venue_id, name=cleaned, kind=label, notes=_clip(notes, 2000, "notes") or "")
    session.add(row)
    session.flush()
    return row


def create_location(session: Session, venue_id: uuid.UUID, name: str, kind: str, notes: str = "") -> Location:
    cleaned = _name(name)
    existing = session.scalar(select(Location).where(Location.venue_id == venue_id, Location.name == cleaned))
    if existing is not None:
        raise Rejected("A location with that name already exists.")
    return ensure_location(session, venue_id, cleaned, kind, notes)


def list_locations(session: Session, venue_id: uuid.UUID) -> list[dict]:
    rows = session.scalars(
        select(Location).where(Location.venue_id == venue_id).order_by(Location.name, Location.id)
    ).all()
    return [location_public(row) for row in rows]


def ensure_bin(session: Session, venue_id: uuid.UUID, location_id: uuid.UUID, code: str, label: str = "") -> Bin:
    place = _location(session, venue_id, location_id)
    cleaned = _code(code)
    existing = session.scalar(select(Bin).where(Bin.venue_id == venue_id, Bin.code == cleaned))
    if existing is not None:
        if existing.location_id != place.id:
            raise Rejected("That bin code is already used in another location.")
        return existing
    row = Bin(
        venue_id=venue_id,
        location_id=place.id,
        code=cleaned,
        label=(_clip(label, 200, "label") or cleaned),
        qr_payload=bin_payload(venue_id, cleaned),
    )
    session.add(row)
    session.flush()
    return row


def create_bin(session: Session, venue_id: uuid.UUID, location_id: uuid.UUID, code: str, label: str = "") -> Bin:
    cleaned = _code(code)
    existing = session.scalar(select(Bin).where(Bin.venue_id == venue_id, Bin.code == cleaned))
    if existing is not None:
        raise Rejected("A bin with that code already exists.")
    return ensure_bin(session, venue_id, location_id, cleaned, label)


def list_bins(session: Session, venue_id: uuid.UUID, location_id: uuid.UUID | None = None) -> list[dict]:
    stmt = select(Bin, Location.name).join(Location, Location.id == Bin.location_id).where(Bin.venue_id == venue_id)
    if location_id is not None:
        _location(session, venue_id, location_id)
        stmt = stmt.where(Bin.location_id == location_id)
    stmt = stmt.order_by(Bin.code, Bin.id)
    return [bin_public(row, name) for row, name in session.execute(stmt).all()]


def bin_label_svg(session: Session, venue_id: uuid.UUID, bin_id: uuid.UUID) -> dict:
    row = session.get(Bin, bin_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("bin not found")
    payload = row.qr_payload or bin_payload(venue_id, row.code)
    return {
        "bin_id": str(row.id),
        "code": row.code,
        "label": row.label,
        "qr_payload": payload,
        "svg": qr_svg(payload),
    }


def list_movements(
    session: Session,
    venue_id: uuid.UUID,
    *,
    sku: str | None = None,
    location_id: uuid.UUID | None = None,
    movement_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
) -> list[dict]:
    stmt = (
        select(StockMovement, Sku.barcode, Product.name, Location.name, Bin.code)
        .join(Sku, Sku.id == StockMovement.sku_id)
        .join(ProductVariant, ProductVariant.id == Sku.product_variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Location, Location.id == StockMovement.location_id)
        .outerjoin(Bin, Bin.id == StockMovement.bin_id)
        .where(StockMovement.venue_id == venue_id)
    )
    if sku:
        code = sku.strip().upper()
        if code:
            stmt = stmt.where(func.upper(Sku.barcode) == code)
    if location_id is not None:
        _location(session, venue_id, location_id)
        stmt = stmt.where(StockMovement.location_id == location_id)
    if movement_type:
        kind = movement_type.strip()
        if kind not in MOVEMENT_TYPES:
            raise Rejected("movement_type is not recognized")
        stmt = stmt.where(StockMovement.movement_type == kind)
    if since is not None:
        stmt = stmt.where(StockMovement.created_at >= _when(since))
    if until is not None:
        stmt = stmt.where(StockMovement.created_at <= _when(until))
    bounded = min(max(int(limit or 100), 1), 500)
    stmt = stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(bounded)
    return [movement_public(row, barcode, name, place, bin_code) for row, barcode, name, place, bin_code in session.execute(stmt).all()]


def _pos_sales_are_source(session: Session, venue_id: uuid.UUID) -> bool:
    """True when this venue's depletion should come from POS sale movements."""

    from madira.models import PosConnection

    row = session.scalar(
        select(PosConnection.id)
        .where(PosConnection.venue_id == venue_id, PosConnection.status == "active")
        .limit(1)
    )
    return row is not None


def depletion_by_sku(session: Session, venue_id: uuid.UUID, *, now: datetime | None = None) -> dict[uuid.UUID, Decimal]:
    """Trailing 30-day depletion. See the module docstring for the source switch."""

    moment = _when(now)
    cutoff = moment - timedelta(days=30)
    rows = session.execute(
        select(StockMovement.sku_id, StockMovement.movement_type, StockMovement.quantity).where(
            StockMovement.venue_id == venue_id,
            StockMovement.created_at >= cutoff,
        )
    ).all()
    pos = _pos_sales_are_source(session, venue_id)
    sales: dict[uuid.UUID, Decimal] = {}
    counts: dict[uuid.UUID, Decimal] = {}
    shrink: dict[uuid.UUID, Decimal] = {}
    sold: set[uuid.UUID] = set()
    for sku_id, kind, quantity in rows:
        qty = as_qty(quantity)
        if kind == "sale":
            sold.add(sku_id)
            sales[sku_id] = sales.get(sku_id, Decimal("0")) + abs(qty)
        elif not pos and kind == "count_adjustment" and qty < 0:
            counts[sku_id] = counts.get(sku_id, Decimal("0")) + abs(qty)
        elif not pos and kind in _SHRINK and qty < 0:
            shrink[sku_id] = shrink.get(sku_id, Decimal("0")) + abs(qty)
    if pos:
        return {sku_id: sales.get(sku_id, Decimal("0")) for sku_id in sold}
    found = set(sales) | set(counts) | set(shrink) | sold
    out: dict[uuid.UUID, Decimal] = {}
    for sku_id in found:
        if sku_id in sold:
            out[sku_id] = sales.get(sku_id, Decimal("0"))
        else:
            out[sku_id] = counts.get(sku_id, Decimal("0")) + shrink.get(sku_id, Decimal("0"))
    return out


def balances_by_sku(session: Session, venue_id: uuid.UUID) -> dict[uuid.UUID, dict[uuid.UUID, Decimal]]:
    rows = session.execute(
        select(StockMovement.sku_id, StockMovement.location_id, func.sum(StockMovement.quantity))
        .where(StockMovement.venue_id == venue_id)
        .group_by(StockMovement.sku_id, StockMovement.location_id)
    ).all()
    out: dict[uuid.UUID, dict[uuid.UUID, Decimal]] = {}
    for sku_id, location_id, total in rows:
        out.setdefault(sku_id, {})[location_id] = as_qty(total or 0)
    return out


def location_public(row: Location) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "kind": row.kind,
        "notes": row.notes or "",
        "created_at": row.created_at,
    }


def bin_public(row: Bin, location_name: str) -> dict:
    return {
        "id": str(row.id),
        "location_id": str(row.location_id),
        "location_name": location_name,
        "code": row.code,
        "label": row.label,
        "qr_payload": row.qr_payload,
        "created_at": row.created_at,
    }


def movement_public(row: StockMovement, barcode: str, name: str, location_name: str, bin_code: str | None) -> dict:
    return {
        "id": str(row.id),
        "sku_id": str(row.sku_id),
        "sku": barcode,
        "name": name,
        "location_id": str(row.location_id),
        "location_name": location_name,
        "bin_id": None if row.bin_id is None else str(row.bin_id),
        "bin_code": bin_code or "",
        "quantity": public_qty(row.quantity),
        "movement_type": row.movement_type,
        "unit_cost_cents": row.unit_cost_cents,
        "source_type": row.source_type or "",
        "source_id": row.source_id or "",
        "reason": row.reason or "",
        "actor_user_id": None if row.actor_user_id is None else str(row.actor_user_id),
        "created_at": row.created_at,
    }


def _name(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned or len(cleaned) > 200:
        raise Rejected("location name is required")
    return cleaned


def _kind(value: str) -> str:
    kind = (value or "").strip()
    if kind not in LOCATION_KINDS:
        raise Rejected("location kind must be cellar, bar, walk_in, storage, or other")
    return kind


def _code(value: str) -> str:
    cleaned = (value or "").strip().upper()
    if not _CODE.match(cleaned):
        raise Rejected("bin code must be letters, numbers, hyphens, or underscores")
    return cleaned
