"""Deterministic tasting-note drafts for demo mode.

The same catalog product always produces the same note and service card.
A producer tech sheet in the prompt is ignored here: it is untrusted data,
not a source of instructions or of extra sentences.
"""

from __future__ import annotations

import json

from madira.domain.catalog.identity import clean

_RED = ("nebbiolo", "pinot noir", "cabernet", "syrah", "merlot", "sangiovese", "red")


def product_from_prompt(prompt: str) -> dict:
    marker = "PRODUCT_JSON="
    start = prompt.find(marker)
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(prompt[start + len(marker) :])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _kind(category: str, style: str) -> str:
    cat = category.casefold()
    styled = style.casefold()
    if cat == "beer":
        return "beer"
    if cat in {"spirit", "spirits"}:
        return "spirit"
    if cat == "sake":
        return "sake"
    if "sparkling" in cat or "sparkling" in styled or "champagne" in styled:
        return "sparkling"
    if cat == "red" or any(word in styled for word in _RED):
        return "red"
    return "white"


def _pick(current: str, allowed: tuple[str, ...], default: str) -> str:
    value = clean(current).casefold()
    if value in allowed:
        return value
    return default


def _profile(product: dict, kind: str) -> dict:
    defaults = {
        "beer": ("light", "medium", "none", "dry", "none", "medium", ["grain", "herbal"]),
        "spirit": ("full", "low", "none", "dry", "light", "pronounced", ["spice", "oak"]),
        "sake": ("light", "medium", "none", "off-dry", "none", "subtle", ["melon", "rice"]),
        "sparkling": ("light", "high", "none", "dry", "none", "medium", ["citrus", "brioche"]),
        "red": ("full", "medium", "high", "dry", "light", "pronounced", ["cherry", "earth"]),
        "white": ("light", "high", "none", "dry", "none", "medium", ["citrus", "mineral"]),
    }[kind]
    families = product.get("aroma_families")
    names = [clean(item) for item in families if clean(item)] if isinstance(families, list) else []
    names = [item for item in names if len(item) <= 40][:6]
    return {
        "body": _pick(str(product.get("body") or ""), ("light", "medium", "full"), defaults[0]),
        "acidity": _pick(str(product.get("acidity") or ""), ("low", "medium", "high"), defaults[1]),
        "tannin": _pick(str(product.get("tannin") or ""), ("none", "low", "medium", "high"), defaults[2]),
        "sweetness": _pick(
            str(product.get("sweetness") or ""),
            ("bone-dry", "dry", "off-dry", "medium-sweet", "sweet"),
            defaults[3],
        ),
        "oak": _pick(str(product.get("oak") or ""), ("none", "light", "medium", "heavy"), defaults[4]),
        "intensity": _pick(
            str(product.get("intensity") or ""),
            ("subtle", "medium", "pronounced"),
            defaults[5],
        ),
        "aroma_families": names or list(defaults[6]),
    }


def _service(kind: str) -> dict[str, str]:
    if kind == "beer":
        return {
            "serving_temperature": "45°F",
            "glassware": "Tulip glass",
            "decanting": "No decant",
            "pour_size": "12 oz",
        }
    if kind == "spirit":
        return {
            "serving_temperature": "Room temperature",
            "glassware": "Copita",
            "decanting": "No decant",
            "pour_size": "2 oz",
        }
    if kind == "sake":
        return {
            "serving_temperature": "50°F",
            "glassware": "Ochoko",
            "decanting": "No decant",
            "pour_size": "4 oz",
        }
    if kind == "sparkling":
        return {
            "serving_temperature": "40-45°F",
            "glassware": "Flute",
            "decanting": "No decant",
            "pour_size": "5 oz",
        }
    if kind == "red":
        return {
            "serving_temperature": "60-65°F",
            "glassware": "Bordeaux glass",
            "decanting": "Decant 30 minutes",
            "pour_size": "5 oz",
        }
    return {
        "serving_temperature": "45-50°F",
        "glassware": "White wine glass",
        "decanting": "No decant",
        "pour_size": "5 oz",
    }


def _hook(name: str, style: str, region: str, category: str) -> str:
    detail = style or category or "house pour"
    place = region or "the list"
    hook = f"{name}: {detail} from {place}, ready to pour."
    if len(hook) <= 160:
        return hook
    hook = f"{name}: ready to pour."
    if len(hook) <= 160:
        return hook
    return "Ready to pour."


def _guest(name: str, producer: str, region: str, style: str) -> str:
    who = producer or "the house"
    where = region or "the cellar"
    what = style or "this pour"
    text = (
        f"{name} from {who} in {where} is {what} with a clean line and a quiet finish. "
        "Offer one precise glass when a guest wants the shape of the bottle before the first sip."
    )
    if len(text.split()) > 45:
        text = (
            f"{name} is a focused glass with a clean line and a quiet finish. "
            "Offer it when a guest wants one precise picture of the bottle before the first sip."
        )
    if len(text.split()) > 45:
        text = (
            "This pour is a focused glass with a clean line and a quiet finish. "
            "Offer it when a guest wants one precise picture of the bottle before the first sip."
        )
    return " ".join(text.split())


def _technical(product: dict, profile: dict) -> str:
    name = clean(product.get("name")) or "This bottle"
    category = clean(product.get("category")) or "a beverage"
    producer = clean(product.get("producer"))
    region = clean(product.get("region"))
    style = clean(product.get("style"))
    place = f" from {producer}" if producer else ""
    where = f" in {region}" if region else ""
    styled = f" ({style})" if style else ""
    aromas = ", ".join(profile["aroma_families"])
    return (
        f"{name} is listed as {category}{place}{where}{styled}. "
        f"The draft profile reads {profile['body']} body, {profile['acidity']} acidity, "
        f"{profile['tannin']} tannin, {profile['sweetness']} sweetness, {profile['oak']} oak, "
        f"and {profile['intensity']} intensity, with {aromas} on the nose. "
        "This note is a draft for the sommelier to edit and approve before it reaches the floor."
    )


def note_draft_payload(product: dict) -> dict:
    name = clean(product.get("name")) or "This bottle"
    category = clean(product.get("category"))
    style = clean(product.get("style"))
    region = clean(product.get("region"))
    producer = clean(product.get("producer"))
    kind = _kind(category, style)
    profile = _profile(product, kind)
    return {
        "server_hook": _hook(name, style, region, category),
        "guest_description": _guest(name, producer, region, style),
        "technical_note": _technical(product, profile),
        **profile,
        **_service(kind),
    }


def note_draft_json(prompt: str) -> str:
    product = product_from_prompt(prompt)
    if not clean(product.get("name")):
        return "{}"
    return json.dumps(note_draft_payload(product), ensure_ascii=False)
