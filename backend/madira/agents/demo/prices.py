"""Deterministic price-sheet rows for the demo model.

Live mode never imports this. A sheet whose text is already a table is parsed
as that table. Anything else returns the house fixture, which the offer
service then matches against the catalog. Unmatched names stay unmatched.
"""

from __future__ import annotations

import csv
import io
import json
import re

_FIXTURE_ROWS = [
    {
        "name": "Muscadet Domaine de l'Ecu",
        "producer": "",
        "sku": "W-MUS-01",
        "unit": "750ml bottle",
        "case_size": "12",
        "price": "19.50",
        "currency": "USD",
    },
    {
        "name": "Barolo G.D. Vajra 2019",
        "producer": "",
        "sku": "W-BAR-01",
        "unit": "750ml bottle",
        "case_size": "6",
        "price": "44.00",
        "currency": "USD",
    },
    {
        "name": "Chateau Nowhere 2015",
        "producer": "",
        "sku": "",
        "unit": "750ml bottle",
        "case_size": "12",
        "price": "30.00",
        "currency": "USD",
    },
]

_TEXT = re.compile(r"PRICE_SHEET_TEXT<<<\n(?P<body>.*?)\n>>>", re.DOTALL)


def price_sheet_json(prompt: str) -> str:
    text = _sheet_text(prompt)
    rows = _table_rows(text)
    if not rows:
        rows = [dict(row) for row in _FIXTURE_ROWS]
    return json.dumps({"rows": rows})


def _sheet_text(prompt: str) -> str:
    match = _TEXT.search(prompt or "")
    if match:
        return match.group("body")
    return prompt or ""


def _table_rows(text: str) -> list[dict]:
    stripped = (text or "").strip()
    if not stripped:
        return []
    blob = _json_rows(stripped)
    if blob:
        return blob
    return _csv_rows(stripped)


def _json_rows(text: str) -> list[dict]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    rows = parsed.get("rows") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _csv_rows(text: str) -> list[dict]:
    sample = text.lstrip()
    header = sample.splitlines()[0].lower() if sample else ""
    if "," not in header or ("name" not in header and "price" not in header and "sku" not in header):
        return []
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        return []
    found = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        cleaned = {str(key or "").strip(): (value or "").strip() for key, value in row.items() if key}
        if any(cleaned.values()):
            found.append(cleaned)
    return found
