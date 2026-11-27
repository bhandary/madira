"""Import a beverage list from a CSV file.

The catalog is built from the venue's own file. Nothing here calls a model,
and the cell values are stored as data.

Header row, matched without case. Spaces, underscores, and hyphens are
ignored, and unknown columns are ignored. Canonical headers:

    section, name, producer, vintage, region, country, category, style,
    grape, bottle size, bottle price, glass price, cost, barcode

Aliases: list section; wine, product, beverage, item; winery, brewery,
maker, brand; year; appellation; type; varietal, variety, grapes; size,
format; glass, pour, pour price, by the glass; unit cost, bottle cost;
sku, upc, ean.

Prices are major units in the venue's currency (``18`` or ``18.50``). A
blank price is zero. Currency is not a column. A product matches an
existing one when normalized producer, name, and category agree. When
several products share that key, the one that already has the vintage and
bottle size is used; otherwise the smallest id is used. The variant matches
on vintage and bottle size. Vintage uses the catalog's whitespace and case
folding. Bottle size also ignores spaces, so ``750 ML`` matches ``750ml``.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from madira.domain.catalog.identity import clean, norm
from madira.domain.errors import NotFound
from madira.domain.lists.service import item_view
from madira.domain.session import session_scope
from madira.models import BeverageList, ListItem, Product, ProductVariant, Sku, Venue
from madira.money import DEFAULT_CURRENCY, bottle_multiple, margin_percent, pour_multiple, to_minor
from madira.storage import get_storage

CSV_TYPES = frozenset(
    {
        "text/csv",
        "application/csv",
        "text/plain",
        "text/comma-separated-values",
        "application/vnd.ms-excel",
    }
)

DOCUMENTED_HEADERS = (
    "section",
    "name",
    "producer",
    "vintage",
    "region",
    "country",
    "category",
    "style",
    "grape",
    "bottle size",
    "bottle price",
    "glass price",
    "cost",
    "barcode",
)

_ALIASES = {
    "section": "section",
    "listsection": "section",
    "name": "name",
    "wine": "name",
    "product": "name",
    "beverage": "name",
    "item": "name",
    "producer": "producer",
    "winery": "producer",
    "brewery": "producer",
    "maker": "producer",
    "brand": "producer",
    "vintage": "vintage",
    "year": "vintage",
    "region": "region",
    "appellation": "region",
    "country": "country",
    "category": "category",
    "type": "category",
    "style": "style",
    "grape": "grape",
    "varietal": "grape",
    "variety": "grape",
    "grapes": "grape",
    "bottlesize": "bottle_size",
    "size": "bottle_size",
    "format": "bottle_size",
    "bottleprice": "bottle_price",
    "glassprice": "glass_price",
    "glass": "glass_price",
    "pour": "glass_price",
    "pourprice": "glass_price",
    "bytheglass": "glass_price",
    "cost": "cost",
    "unitcost": "cost",
    "bottlecost": "cost",
    "barcode": "barcode",
    "sku": "barcode",
    "upc": "barcode",
    "ean": "barcode",
}

_LIMITS = {
    "section": 200,
    "name": 200,
    "producer": 200,
    "vintage": 32,
    "region": 200,
    "country": 80,
    "category": 32,
    "style": 200,
    "grape": 200,
    "bottle_size": 32,
    "barcode": 64,
}

_LABELS = {
    "section": "Section",
    "name": "Name",
    "producer": "Producer",
    "vintage": "Vintage",
    "region": "Region",
    "country": "Country",
    "category": "Category",
    "style": "Style",
    "grape": "Grape",
    "bottle_size": "Bottle size",
    "barcode": "Barcode",
    "bottle_price": "Bottle price",
    "glass_price": "Glass price",
    "cost": "Cost",
}

_MAX_ROWS = 2000
_MAX_MINOR = 100_000_000
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


class ImportRejected(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ParsedRow:
    line: int
    section: str = ""
    name: str = ""
    producer: str = ""
    vintage: str = ""
    region: str = ""
    country: str = ""
    category: str = ""
    style: str = ""
    grape: str = ""
    bottle_size: str = ""
    bottle_price: int = 0
    glass_price: int = 0
    cost: int = 0
    barcode: str = ""
    error: str = ""


@dataclass
class Outcome:
    line: int
    status: str
    action: str
    message: str
    section: str
    name: str
    producer: str
    category: str
    vintage: str
    bottle_size: str
    sku: Sku | None = None
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None

    def public(self) -> dict:
        return {
            "line": self.line,
            "status": self.status,
            "action": self.action,
            "message": self.message,
            "section": self.section,
            "name": self.name,
            "producer": self.producer,
            "category": self.category,
            "vintage": self.vintage,
            "bottle_size": self.bottle_size,
            "product_id": self.product_id,
            "variant_id": self.variant_id,
        }


def import_csv(
    venue_id: uuid.UUID,
    *,
    filename: str,
    body: bytes,
    content_type: str | None,
    confirm: bool,
    name: str = "",
) -> dict:
    storage = get_storage()
    storage.check(
        body=body,
        content_type=content_type,
        filename=filename,
        allowed_types=CSV_TYPES,
        fallback_extension=".csv",
    )
    parsed = _parse(body)
    list_title, safe_name = _list_name(filename, name)
    with session_scope() as session:
        if not confirm:
            outcomes = _apply(session, venue_id, parsed, write=False)
            currency = _currency(session, venue_id)
            return _summary(outcomes, currency, mode="preview")
        outcomes = _apply(session, venue_id, parsed, write=False)
        accepted = [row for row in outcomes if row.status != "error"]
        if not accepted:
            raise ImportRejected("Nothing to import. Fix the rows in the preview and try again.")
        stored = storage.put(
            venue_id,
            kind="lists",
            body=body,
            content_type=content_type,
            filename=filename,
            allowed_types=CSV_TYPES,
            fallback_extension=".csv",
        )
        try:
            written = _apply(session, venue_id, parsed, write=True)
            currency = _currency(session, venue_id)
            beverage_list = BeverageList(
                venue_id=venue_id,
                name=list_title,
                budget=0,
                currency=currency,
                target_margin=0,
                notes=f"Imported from {safe_name}.",
                source_key=stored.key,
                source_filename=safe_name,
            )
            session.add(beverage_list)
            session.flush()
            position = 0
            items: list[ListItem] = []
            for outcome in written:
                if outcome.status == "error" or outcome.sku is None:
                    continue
                position += 1
                parsed_row = next(row for row in parsed if row.line == outcome.line)
                item = ListItem(
                    venue_id=venue_id,
                    list_id=beverage_list.id,
                    sku_id=outcome.sku.id,
                    section=parsed_row.section,
                    position=position,
                    cost=parsed_row.cost,
                    pour_price=parsed_row.glass_price,
                    bottle_price=parsed_row.bottle_price,
                    currency=currency,
                    margin_pct=_margin(parsed_row.glass_price, parsed_row.bottle_price, parsed_row.cost),
                )
                item.sku = outcome.sku
                session.add(item)
                items.append(item)
            session.flush()
            payload = _summary(written, currency, mode="confirmed")
            payload["list"] = {
                "id": beverage_list.id,
                "name": beverage_list.name,
                "currency": currency,
                "item_count": len(items),
                "source_key": stored.key,
                "source_filename": safe_name,
                "items": [item_view(item) for item in items],
            }
            session.commit()
            return payload
        except IntegrityError as exc:
            session.rollback()
            storage.delete(stored.key)
            raise ImportRejected("This import conflicts with a bottle already in the catalog.") from exc
        except Exception:
            session.rollback()
            storage.delete(stored.key)
            raise


def _summary(outcomes: list[Outcome], currency: str, *, mode: str) -> dict:
    new_products = sum(1 for row in outcomes if row.action == "new_product")
    new_variants = sum(1 for row in outcomes if row.action == "new_variant")
    return {
        "mode": mode,
        "currency": currency,
        "matched": sum(1 for row in outcomes if row.status == "match"),
        "new": sum(1 for row in outcomes if row.status == "new"),
        "new_products": new_products,
        "new_variants": new_variants,
        "errors": sum(1 for row in outcomes if row.status == "error"),
        "rows": [row.public() for row in outcomes],
    }


def _parse(body: bytes) -> list[ParsedRow]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportRejected("This file is not UTF-8 text.") from exc
    sample = text.lstrip("\ufeff")
    header_line = sample.splitlines()[0] if sample.strip() else ""
    delimiter = ";" if header_line.count(";") > header_line.count(",") else ","
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        fields = _header_map(reader.fieldnames)
        parsed: list[ParsedRow] = []
        for line, raw in enumerate(reader, start=2):
            if line > _MAX_ROWS + 1:
                raise ImportRejected(f"This CSV has more than {_MAX_ROWS} rows.")
            row = _row(line, raw, fields)
            if row is not None:
                parsed.append(row)
    except csv.Error as exc:
        raise ImportRejected("This file could not be read as CSV.") from exc
    return parsed


def _header_map(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames or not any(clean(name) for name in fieldnames if name):
        raise ImportRejected("The CSV needs a header row.")
    present = [name for name in fieldnames if name and clean(name)]
    if len(present) > 100:
        raise ImportRejected("This CSV has too many columns.")
    if len(present) != len({clean(name).casefold() for name in present}):
        raise ImportRejected("The header row repeats a column.")
    mapped: dict[str, str] = {}
    seen: set[str] = set()
    for original in present:
        key = re.sub(r"[^a-z0-9]+", "", original.casefold())
        field = _ALIASES.get(key)
        if field is None:
            continue
        if field in seen:
            raise ImportRejected(f"The column {clean(original)} is repeated.")
        seen.add(field)
        mapped[field] = original
    if "name" not in mapped:
        raise ImportRejected("The CSV needs a name column.")
    return mapped


def _row(line: int, raw: dict, fields: dict[str, str]) -> ParsedRow | None:
    values = {field: _cell(raw, original) for field, original in fields.items()}
    if not any(clean(value) for value in values.values()):
        return None
    row = ParsedRow(line=line)
    problems: list[str] = []
    for field in (
        "section",
        "name",
        "producer",
        "vintage",
        "region",
        "country",
        "category",
        "style",
        "grape",
        "bottle_size",
    ):
        value = clean(values.get(field, ""))
        if field == "bottle_size":
            value = "".join(value.split())
        if len(value) > _LIMITS[field]:
            problems.append(f"{_LABELS[field]} is too long.")
        setattr(row, field, value)
    barcode = "".join(clean(values.get("barcode", "")).split()).upper()
    if len(barcode) > _LIMITS["barcode"]:
        problems.append("Barcode is too long.")
    row.barcode = barcode
    for field in ("bottle_price", "glass_price", "cost"):
        amount, problem = _price(values.get(field, ""), _LABELS[field])
        setattr(row, field, amount)
        if problem:
            problems.append(problem)
    if not row.name:
        problems.append("Name is required.")
    row.error = " ".join(problems)
    return row


def _cell(raw: dict, original: str) -> str:
    value = raw.get(original)
    if value is None:
        return ""
    return str(value)


def _price(raw: str, label: str) -> tuple[int, str]:
    text = clean(raw).replace(",", "")
    text = re.sub(r"[$€£¥]", "", text)
    text = re.sub(r"\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF)\b", "", text, flags=re.IGNORECASE)
    text = clean(text)
    if not text:
        return 0, ""
    if not _NUMBER.match(text):
        return 0, f"{label} must be a number."
    try:
        minor = to_minor(text)
    except (ArithmeticError, TypeError, ValueError):
        return 0, f"{label} must be a number."
    if minor < 0:
        return 0, f"{label} cannot be negative."
    if minor > _MAX_MINOR:
        return 0, f"{label} is too large."
    return minor, ""


def _apply(session, venue_id: uuid.UUID, rows: list[ParsedRow], *, write: bool) -> list[Outcome]:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    grouped = _grouped_products(session, venue.organization_id)
    product_ids = [product.id for group in grouped.values() for product in group]
    variants: dict[tuple[uuid.UUID, tuple[str, str]], ProductVariant] = {}
    if product_ids:
        found = session.scalars(select(ProductVariant).where(ProductVariant.product_id.in_(product_ids))).all()
        for variant in found:
            variants[(variant.product_id, _import_variant_key(variant.vintage, variant.bottle_size))] = variant
    skus = {
        sku.product_variant_id: sku
        for sku in session.scalars(select(Sku).where(Sku.venue_id == venue_id)).all()
    }
    barcodes = {sku.barcode: sku.id for sku in skus.values() if sku.barcode}
    planned: set[tuple[str, str, str]] = set()
    pending_barcodes: set[str] = set()
    seen: set[tuple] = set()
    outcomes: list[Outcome] = []

    for row in rows:
        if row.error:
            outcomes.append(_error(row, row.error, "error"))
            continue
        pkey = _product_key(row)
        vkey = _import_variant_key(row.vintage, row.bottle_size)
        identity = (pkey, vkey)
        if identity in seen:
            outcomes.append(_error(row, "Duplicate of an earlier row.", "duplicate"))
            continue
        product = _pick_product(grouped.get(pkey, []), vkey, variants)
        variant = variants.get((product.id, vkey)) if product is not None else None
        if not grouped.get(pkey) and pkey not in planned:
            action = "new_product"
        elif variant is None:
            action = "new_variant"
        else:
            action = "existing"
        sku = skus.get(variant.id) if variant is not None else None
        if sku is None and row.barcode and (row.barcode in barcodes or row.barcode in pending_barcodes):
            outcomes.append(_error(row, "Barcode is already used by another bottle.", "error"))
            continue
        seen.add(identity)
        if action == "new_product":
            planned.add(pkey)
        if sku is None and row.barcode:
            pending_barcodes.add(row.barcode)
        if write:
            product, variant, sku = _ensure(session, venue, row, product=product, variant=variant, sku=sku)
            group = grouped.setdefault(pkey, [])
            if product not in group:
                group.append(product)
                group.sort(key=lambda item: str(item.id))
            variants[(product.id, vkey)] = variant
            skus[variant.id] = sku
            if sku.barcode:
                barcodes[sku.barcode] = sku.id
        status = "match" if action == "existing" else "new"
        message = {
            "existing": "Matched an existing product and variant.",
            "new_product": "New product.",
            "new_variant": "New variant of an existing product.",
        }[action]
        outcomes.append(
            Outcome(
                line=row.line,
                status=status,
                action=action,
                message=message,
                section=row.section,
                name=row.name,
                producer=row.producer,
                category=row.category,
                vintage=row.vintage,
                bottle_size=row.bottle_size,
                sku=sku if write else None,
                product_id=product.id if isinstance(product, Product) else None,
                variant_id=variant.id if variant is not None else None,
            )
        )
    return outcomes


def _ensure(
    session,
    venue: Venue,
    row: ParsedRow,
    *,
    product: Product | None,
    variant: ProductVariant | None,
    sku: Sku | None,
) -> tuple[Product, ProductVariant, Sku]:
    if product is None:
        product = Product(
            organization_id=venue.organization_id,
            category=row.category,
            producer=row.producer,
            name=row.name,
            region=row.region,
            country=row.country,
            style=row.style,
            grape=row.grape,
            aroma_families=[],
        )
        session.add(product)
        session.flush()
    if variant is None:
        variant = ProductVariant(product_id=product.id, vintage=row.vintage, bottle_size=row.bottle_size)
        variant.product = product
        session.add(variant)
        session.flush()
    if sku is None:
        sku = Sku(
            venue_id=venue.id,
            product_variant_id=variant.id,
            barcode=row.barcode,
            cost=row.cost,
            currency=_code(venue.currency),
        )
        sku.variant = variant
        session.add(sku)
        session.flush()
    from madira.domain.embeddings.schedule import mark

    mark(session, venue.id, venue.organization_id, "sku", sku.id)
    return product, variant, sku


def _grouped_products(session, organization_id: uuid.UUID) -> dict[tuple[str, str, str], list[Product]]:
    grouped: dict[tuple[str, str, str], list[Product]] = {}
    rows = session.scalars(select(Product).where(Product.organization_id == organization_id)).all()
    for product in rows:
        grouped.setdefault(_product_key(product), []).append(product)
    for group in grouped.values():
        group.sort(key=lambda item: str(item.id))
    return grouped


def _pick_product(
    group: list[Product],
    vkey: tuple[str, str],
    variants: dict[tuple[uuid.UUID, tuple[str, str]], ProductVariant],
) -> Product | None:
    if not group:
        return None
    holding = [product for product in group if (product.id, vkey) in variants]
    return holding[0] if holding else group[0]


def _product_key(row: Product | ParsedRow) -> tuple[str, str, str]:
    return (norm(row.category), norm(row.producer), norm(row.name))


def _import_variant_key(vintage: str, bottle_size: str) -> tuple[str, str]:
    return (norm(vintage), "".join(norm(bottle_size).split()))


def _error(row: ParsedRow, message: str, action: str) -> Outcome:
    return Outcome(
        line=row.line,
        status="error",
        action=action,
        message=message,
        section=row.section,
        name=row.name,
        producer=row.producer,
        category=row.category,
        vintage=row.vintage,
        bottle_size=row.bottle_size,
    )


def _currency(session, venue_id: uuid.UUID) -> str:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return _code(venue.currency)


def _code(value: str | None) -> str:
    code = clean(value).upper()
    if len(code) == 3 and code.isalpha():
        return code
    return DEFAULT_CURRENCY


def _margin(glass: int, bottle: int, cost: int) -> float:
    if glass > 0:
        multiple = pour_multiple(glass, cost)
    elif bottle > 0:
        multiple = bottle_multiple(bottle, cost)
    else:
        return 0.0
    return float(margin_percent(multiple))


def _list_name(filename: str, requested: str) -> tuple[str, str]:
    safe = _safe_filename(filename)
    requested_clean = clean(requested)[:200]
    if requested_clean:
        return requested_clean, safe
    stem = Path(safe).stem.replace("_", " ").strip()
    return (stem or "Imported list")[:200], safe


def _safe_filename(filename: str) -> str:
    base = Path(filename or "").name
    base = "".join(ch for ch in base if ch.isprintable() and ch not in "\\/")
    base = clean(base)
    return (base or "list.csv")[:200]
