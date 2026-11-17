"""Structured menu extraction.

The model returns one object. It is checked against this schema, and on
failure it is asked once more. A second failure is a clear error. Uploaded
text is data in the prompt, not a set of instructions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

from madira.domain.errors import DraftFailed

TEXT_FIELDS = ("name", "course", "main_component", "cooking_method", "sauce")
SCORE_FIELDS = ("richness", "acidity", "sweetness", "spice", "umami")
CONFIDENCE_FIELDS = TEXT_FIELDS + ("price",) + SCORE_FIELDS + ("allergens",)
LOW_CONFIDENCE = 0.6
EDITABLE_FIELDS = CONFIDENCE_FIELDS

SCHEMA_HINT = (
    "JSON keys: name, cuisine, price_tier, dishes. "
    "Each dish has name, course, price (integer minor units), main_component, "
    "cooking_method, sauce, richness, acidity, sweetness, spice, umami "
    "(integers 0 to 5), allergens (array of short names), and confidence. "
    "confidence maps every one of those dish field names to a number from 0 to 1."
)

Completer = Callable[[str, tuple[str, bytes] | None], str]


def normalize(value: str) -> str:
    return " ".join((value or "").split()).casefold()


def content_hash(fields: dict) -> str:
    """Hash the fields a later pairing run would use. Confidence is not part of it."""

    body = {
        "name": normalize(str(fields.get("name") or "")),
        "course": normalize(str(fields.get("course") or "")),
        "price": int(fields.get("price") or 0),
        "main_component": normalize(str(fields.get("main_component") or "")),
        "cooking_method": normalize(str(fields.get("cooking_method") or "")),
        "sauce": normalize(str(fields.get("sauce") or "")),
        "richness": int(fields.get("richness") or 0),
        "acidity": int(fields.get("acidity") or 0),
        "sweetness": int(fields.get("sweetness") or 0),
        "spice": int(fields.get("spice") or 0),
        "umami": int(fields.get("umami") or 0),
        "allergens": sorted(normalize(str(item)) for item in (fields.get("allergens") or []) if normalize(str(item))),
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def low_confidence(confidence: dict) -> list[str]:
    flagged = []
    for field in CONFIDENCE_FIELDS:
        try:
            score = float(confidence.get(field, 0))
        except (TypeError, ValueError):
            score = 0
        if score < LOW_CONFIDENCE:
            flagged.append(field)
    return flagged


def _line(value: str, *, limit: int, required: bool) -> str:
    text = " ".join((value or "").split())
    if required and not text:
        raise ValueError("is required")
    if len(text) > limit:
        raise ValueError(f"must be at most {limit} characters")
    return text


class DishDraft(BaseModel):
    name: str
    course: str = ""
    price: int
    main_component: str = ""
    cooking_method: str = ""
    sauce: str = ""
    richness: int
    acidity: int
    sweetness: int
    spice: int
    umami: int
    allergens: list[str] = Field(default_factory=list)
    confidence: dict[str, float]

    @field_validator("name")
    @classmethod
    def dish_name(cls, value: str) -> str:
        return _line(value, limit=200, required=True)

    @field_validator("course")
    @classmethod
    def dish_course(cls, value: str) -> str:
        return _line(value, limit=80, required=False)

    @field_validator("main_component", "cooking_method", "sauce")
    @classmethod
    def dish_text(cls, value: str) -> str:
        return _line(value, limit=200, required=False)

    @field_validator("price")
    @classmethod
    def minor_units(cls, value: int) -> int:
        if isinstance(value, bool) or value < 0 or value > 10_000_000:
            raise ValueError("must be a minor-unit price")
        return int(value)

    @field_validator("richness", "acidity", "sweetness", "spice", "umami")
    @classmethod
    def score(cls, value: int) -> int:
        if isinstance(value, bool) or value < 0 or value > 5:
            raise ValueError("must be from 0 to 5")
        return int(value)

    @field_validator("allergens")
    @classmethod
    def allergen_names(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        folded: set[str] = set()
        for item in value:
            cleaned = " ".join(str(item).split())
            if not cleaned or len(cleaned) > 40:
                raise ValueError("must be 1 to 40 characters")
            key = cleaned.casefold()
            if key in folded:
                continue
            folded.add(key)
            seen.append(cleaned)
        if len(seen) > 12:
            raise ValueError("must list at most 12 allergens")
        return seen

    @field_validator("confidence")
    @classmethod
    def field_confidence(cls, value: dict) -> dict[str, float]:
        if set(value) != set(CONFIDENCE_FIELDS):
            raise ValueError("must include every dish field")
        cleaned: dict[str, float] = {}
        for key in CONFIDENCE_FIELDS:
            number = value[key]
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ValueError("must be a number from 0 to 1")
            if number < 0 or number > 1:
                raise ValueError("must be a number from 0 to 1")
            cleaned[key] = float(number)
        return cleaned


class MenuDraft(BaseModel):
    name: str
    cuisine: str = ""
    price_tier: str = ""
    dishes: list[DishDraft] = Field(min_length=1, max_length=40)

    @field_validator("name")
    @classmethod
    def menu_name(cls, value: str) -> str:
        return _line(value, limit=200, required=True)

    @field_validator("cuisine")
    @classmethod
    def menu_cuisine(cls, value: str) -> str:
        return _line(value, limit=80, required=False)

    @field_validator("price_tier")
    @classmethod
    def menu_tier(cls, value: str) -> str:
        return _line(value, limit=32, required=False)


def _load_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    if start < 0:
        raise json.JSONDecodeError("no object", text, 0)
    data, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(data, dict):
        raise json.JSONDecodeError("not an object", text, start)
    return data


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "draft"
            parts.append(f"{loc}: {err['msg']}")
        return "; ".join(parts)[:500]
    return "The response was not JSON."


def _retry_prompt(prompt: str, error: str) -> str:
    return (
        prompt
        + "\nThe previous JSON did not match the schema. "
        + "Fix these fields and return one JSON object:\n"
        + error
        + "\n"
        + SCHEMA_HINT
        + "\n"
    )


def complete_menu(prompt: str, completer: Completer, image: tuple[str, bytes] | None = None) -> MenuDraft:
    """Validate one completion. On failure, retry once, then raise."""

    error = ""
    for attempt in (1, 2):
        try:
            raw = completer(prompt if attempt == 1 else _retry_prompt(prompt, error), image)
        except DraftFailed:
            raise
        except Exception as exc:
            raise DraftFailed(f"The menu extraction failed ({type(exc).__name__}).", 502) from exc
        try:
            return MenuDraft.model_validate(_load_json(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            error = _safe_error(exc)
    raise DraftFailed("The menu did not match the schema after one retry.")
