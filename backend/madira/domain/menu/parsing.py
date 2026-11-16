"""Line parser for a pasted or uploaded menu. Fixture menus are not used here."""

from __future__ import annotations


def matches_sample_menu(raw: str) -> bool:
    """True when the text is the Maison Madira sample, which the demo maps to fixture dishes."""
    lowered = raw.lower()
    return "dungeness" in lowered or "maison madira" in lowered or ("ribeye" in lowered and "truffle" in lowered)


def line_parse_menu(raw: str, source_name: str) -> dict:
    """Turn dish lines into a menu dict. ``dishes`` is empty when no line qualifies."""
    dishes: list[dict] = []
    course = "course"
    for line in raw.splitlines():
        cleaned = line.strip().lstrip("-•*").strip()
        if not cleaned or len(cleaned) < 4:
            continue
        if cleaned.isupper() and len(cleaned) < 40:
            continue
        if cleaned.lower().startswith("maison"):
            continue
        price = 0.0
        name = cleaned
        if "—" in cleaned:
            left, right = cleaned.rsplit("—", 1)
            name = left.strip()
            try:
                price = float(right.replace("$", "").strip().split()[0])
            except (ValueError, IndexError):
                price = 0.0
        elif "$" in cleaned:
            try:
                price = float(cleaned.split("$")[-1].strip().split()[0])
                name = cleaned.split("$")[0].rstrip(" -—").strip()
            except ValueError:
                price = 0.0
        name = name.lstrip("0123456789.").strip()
        if len(name) < 4:
            continue
        dishes.append(
            {
                "name": name,
                "course": course,
                "description": name,
                "flavor_profile": guess_flavor(name),
                "price": price,
            }
        )
        course = "following"
    lowered = raw.lower()
    cuisine = "California-French" if "french" in lowered else "contemporary"
    return {
        "name": source_name or "Uploaded menu",
        "cuisine": cuisine,
        "price_tier": "$$$",
        "source_type": source_name,
        "raw_text": raw,
        "dishes": dishes[:12],
    }


def guess_flavor(name: str) -> str:
    n = name.lower()
    tags = []
    mapping = {
        "crab": "sweet-briny",
        "fish": "lean ocean",
        "oyster": "saline",
        "duck": "rich game",
        "liver": "umami",
        "beef": "charred fat",
        "ribeye": "charred fat",
        "steak": "charred fat",
        "truffle": "earthy",
        "risotto": "creamy",
        "chocolate": "bitter cocoa",
        "yuzu": "citrus",
        "lemon": "citrus",
        "cherry": "sweet-sour fruit",
        "mushroom": "woodland",
        "lamb": "herbal roast",
        "pork": "sweet-savory",
        "salad": "green acid",
    }
    for key, tag in mapping.items():
        if key in n:
            tags.append(tag)
    return ", ".join(tags) or "savory, balanced"
