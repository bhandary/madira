"""A small PDF 1.4 writer for purchase orders. No system PDF library."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime


def _plain(value) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


def _money(cents: int) -> str:
    sign = "-" if int(cents) < 0 else ""
    amount = abs(int(cents))
    return f"{sign}${amount // 100:,}.{amount % 100:02d}"


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _stamp(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    if isinstance(value, date):
        return value.isoformat()
    return _plain(value)


def render_purchase_order_pdf(po, supplier, contact, lines, venue, approval) -> bytes:
    """Valid ``%PDF-1.4`` bytes for one purchase order."""

    rows = [
        f"Purchase order { _plain(getattr(po, 'po_number', '') or '') }",
        f"Venue: {_plain(getattr(venue, 'name', '') or '')}",
        f"Supplier: {_plain(getattr(supplier, 'name', '') or '')}",
    ]
    if getattr(supplier, "account_number", None):
        rows.append(f"Account: {_plain(supplier.account_number)}")
    if contact is not None:
        bits = [_plain(contact.name)]
        if getattr(contact, "role", None):
            bits.append(_plain(contact.role))
        if getattr(contact, "email", None):
            bits.append(_plain(contact.email))
        if getattr(contact, "phone", None):
            bits.append(_plain(contact.phone))
        rows.append("Contact: " + " · ".join(bit for bit in bits if bit))
    else:
        rows.append("Contact: none on file")
    delivery = getattr(po, "expected_delivery_date", None) or "not set"
    rows.append(f"Expected delivery: {_plain(delivery)}")
    rows.append(f"Status: {_plain(getattr(po, 'status', ''))}")
    rows.append("")
    rows.append("SKU  Name  Cases  Bottles  Unit  Line")
    for line in lines:
        name = getattr(line, "product_name", None) or getattr(line, "name", "")
        unit = int(getattr(line, "unit_cost_cents", 0) or getattr(line, "unit_cost", 0) or 0)
        total = int(getattr(line, "line_total_cents", 0) or 0)
        bottles = getattr(line, "quantity_ordered", None)
        if bottles is None:
            bottles = getattr(line, "qty", 0)
        rows.append(
            "  ".join(
                [
                    _plain(getattr(line, "sku", "")),
                    _plain(name)[:42],
                    str(int(getattr(line, "cases_ordered", 0) or 0)),
                    _plain(bottles),
                    _money(unit),
                    _money(total),
                ]
            )
        )
        if getattr(line, "vintage", None):
            rows.append(f"    Vintage {_plain(line.vintage)}")
    rows.append("")
    subtotal = int(getattr(po, "subtotal_cents", 0) or 0)
    minimum = int(getattr(po, "order_minimum_cents", 0) or 0)
    rows.append(f"Subtotal: {_money(subtotal)}")
    rows.append(f"Order minimum: {_money(minimum)}")
    met = bool(getattr(po, "minimum_met", subtotal >= minimum))
    rows.append(f"Minimum met: {'yes' if met else 'no'}")
    if not met:
        rows.append(f"Shortfall: {_money(max(0, minimum - subtotal))}")
    rows.append("")
    decision = getattr(approval, "decision", None) or "pending"
    required = getattr(approval, "required_role", None) or "owner"
    if decision == "approved":
        who = _plain(getattr(approval, "decided_by_email", None) or getattr(approval, "decided_by_user_id", "") or "Owner")
        when = _stamp(getattr(approval, "decided_at", None))
        rows.append(f"Owner approval: approved ({required}) by {who}" + (f" at {when}" if when else ""))
    elif decision == "rejected":
        rows.append(f"Owner approval: rejected ({required})")
    else:
        rows.append(f"Owner approval: pending ({required})")
    comment = _plain(getattr(approval, "comment", None) or "")
    if comment:
        rows.append(f"Comment: {comment[:180]}")
    if getattr(po, "notes", None):
        rows.append(f"Notes: {_plain(po.notes)[:180]}")
    return _document(rows)


def _document(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
    for index, line in enumerate(lines):
        text = _pdf_escape(_plain(line))[:200]
        if index == 0:
            commands.append(f"({text}) Tj")
        else:
            commands.append("T*")
            commands.append(f"({text}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode("ascii"))
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)
