"""Deterministic menu extraction for demo mode.

The sample menu files always produce the same dishes. Other pasted text is
read line by line. A photo that is not the sample is refused. Nothing in the
uploaded text is treated as an instruction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from madira.domain.errors import DraftFailed
from madira.domain.menu.parsing import line_parse_menu, matches_sample_menu
from madira.domain.menu.schemas import CONFIDENCE_FIELDS, MenuDraft
from madira.money import to_minor

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"
_SAMPLE_FILES = ("sample_menu.png", "sample_menu.pdf", "sample_menu.txt")


def _confidence(**overrides: float) -> dict[str, float]:
    scores = {field: 0.95 for field in CONFIDENCE_FIELDS}
    scores.update(overrides)
    return scores


def _dish(
    name: str,
    course: str,
    price: int,
    main: str,
    method: str,
    sauce: str,
    richness: int,
    acidity: int,
    sweetness: int,
    spice: int,
    umami: int,
    allergens: list[str],
    confidence: dict[str, float] | None = None,
) -> dict:
    return {
        "name": name,
        "course": course,
        "price": price,
        "main_component": main,
        "cooking_method": method,
        "sauce": sauce,
        "richness": richness,
        "acidity": acidity,
        "sweetness": sweetness,
        "spice": spice,
        "umami": umami,
        "allergens": allergens,
        "confidence": _confidence(**(confidence or {})),
    }


_SAMPLE = {
    "name": "Maison Madira — Autumn Tasting",
    "cuisine": "California-French",
    "price_tier": "$$$",
    "dishes": [
        _dish(
            "Dungeness crab, yuzu, avocado, cucumber",
            "cold starter",
            2400,
            "Dungeness crab",
            "raw",
            "yuzu",
            2,
            4,
            2,
            0,
            3,
            ["shellfish"],
            {"sauce": 0.42},
        ),
        _dish(
            "Duck liver mousse, cherry, toasted brioche",
            "hot starter",
            2200,
            "duck liver",
            "whipped",
            "cherry",
            5,
            2,
            3,
            0,
            4,
            ["gluten", "milk"],
        ),
        _dish(
            "Black truffle risotto, aged parmesan, thyme",
            "pasta",
            3600,
            "arborio rice",
            "simmered",
            "parmesan",
            4,
            1,
            1,
            0,
            5,
            ["milk"],
        ),
        _dish(
            "Dry-aged ribeye, bone marrow butter, charred alliums",
            "main",
            5800,
            "ribeye",
            "grilled",
            "bone marrow butter",
            5,
            1,
            1,
            1,
            5,
            ["milk"],
        ),
        _dish(
            "Dark chocolate, smoked salt, Arbequina olive oil",
            "dessert",
            1600,
            "dark chocolate",
            "plated",
            "olive oil",
            4,
            1,
            4,
            0,
            2,
            [],
        ),
    ],
}


def sample_payload() -> dict:
    return MenuDraft.model_validate(_SAMPLE).model_dump()


def fixture_hashes() -> set[str]:
    found = set()
    for name in _SAMPLE_FILES:
        path = FIXTURES / name
        if path.is_file():
            found.add(hashlib.sha256(path.read_bytes()).hexdigest())
    return found


def _value(prompt: str, label: str) -> str:
    prefix = f"{label}="
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _menu_text(prompt: str) -> str:
    start = prompt.find("MENU_TEXT<<<")
    end = prompt.find(">>>", start + 1 if start >= 0 else 0)
    if start < 0 or end < 0:
        return ""
    return prompt[start + len("MENU_TEXT<<<") : end].strip("\n")


def _from_lines(text: str) -> dict:
    parsed = line_parse_menu(text, "Uploaded menu")
    if not parsed["dishes"]:
        raise DraftFailed("No dishes were found in that menu.", 422)
    dishes = []
    for row in parsed["dishes"]:
        name = row["name"]
        component = name.split(",")[0].strip()
        confidence = _confidence(cooking_method=0.4, sauce=0.4)
        dishes.append(
            {
                "name": name,
                "course": row["course"],
                "price": to_minor(row["price"]),
                "main_component": component[:200],
                "cooking_method": "",
                "sauce": "",
                "richness": 2,
                "acidity": 2,
                "sweetness": 1,
                "spice": 0,
                "umami": 2,
                "allergens": [],
                "confidence": confidence,
            }
        )
    return MenuDraft.model_validate(
        {
            "name": parsed["name"],
            "cuisine": parsed["cuisine"],
            "price_tier": parsed["price_tier"],
            "dishes": dishes,
        }
    ).model_dump()


def extraction_json(prompt: str) -> str:
    kind = _value(prompt, "SOURCE_KIND")
    digest = _value(prompt, "SOURCE_SHA256")
    text = _menu_text(prompt)
    if digest and digest in fixture_hashes():
        return json.dumps(sample_payload())
    if matches_sample_menu(text):
        return json.dumps(sample_payload())
    if kind == "photo":
        raise DraftFailed("Demo mode reads the sample menu photo, PDF, and text.", 422)
    return json.dumps(_from_lines(text))
