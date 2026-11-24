"""Deterministic lesson JSON for the staff-trainer demo model.

The ids are copied from the LESSON_GROUNDING prompt. The model does not invent
a standard or a bottle, and the text does not include a price.
"""

from __future__ import annotations

import json
import re


def lesson_draft_json(prompt: str) -> str:
    position = "server"
    standards: list[dict[str, str]] = []
    bottles: list[dict[str, str]] = []
    for line in (prompt or "").splitlines():
        if line.startswith("POSITION "):
            position = line.split(" ", 1)[1].strip() or position
            continue
        standard = re.match(r"STANDARD id=(\S+) slug=\S+ title=(.*)$", line)
        if standard:
            standards.append({"id": standard.group(1), "title": standard.group(2).strip()})
            continue
        bottle = re.match(r"SKU id=(\S+) name=(.*?) glass=(.*?) temperature=(.*?) pour=(.*)$", line)
        if bottle:
            bottles.append(
                {
                    "id": bottle.group(1),
                    "name": bottle.group(2).strip(),
                    "glass": bottle.group(3).strip(),
                    "temperature": bottle.group(4).strip(),
                    "pour": bottle.group(5).strip(),
                }
            )
    if not standards or not bottles:
        return "{}"
    label = "Floor" if position == "all" else position[:1].upper() + position[1:]
    lines = [f"This {position} lesson follows the house standards."]
    for row in standards:
        lines.append(f"Standard: {row['title']}.")
    for row in bottles:
        glass = row["glass"] or "the glass on the card"
        temperature = row["temperature"] or "the temperature on the card"
        pour = row["pour"] or "the pour on the card"
        lines.append(f"{row['name']}: serve in a {glass} at {temperature}, {pour}.")
    return json.dumps(
        {
            "title": f"{label} service: {standards[0]['title']}"[:200],
            "body": " ".join(lines)[:8000],
            "position": position,
            "standard_ids": [row["id"] for row in standards],
            "sku_ids": [row["id"] for row in bottles],
        }
    )
