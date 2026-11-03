"""Deterministic beverage-program fixtures used by demo mode and seed."""

from __future__ import annotations

SAMPLE_MENU_TEXT = """\
MAISON MADIRA — Autumn Tasting Menu
California-French · Price tier: $$$

1. Dungeness crab, yuzu, avocado, cucumber — $24
2. Duck liver mousse, cherry, toasted brioche — $22
3. Black truffle risotto, aged parmesan, thyme — $36
4. Dry-aged ribeye, bone marrow butter, charred alliums — $58
5. Dark chocolate, smoked salt, Arbequina olive oil — $16
"""

SAMPLE_DISHES = [
    {
        "name": "Dungeness crab, yuzu, avocado, cucumber",
        "course": "cold starter",
        "description": "Sweet Dungeness with yuzu brightness and cool cucumber.",
        "flavor_profile": "sweet-briny, citrus, cool fat, green",
        "price": 24.0,
    },
    {
        "name": "Duck liver mousse, cherry, toasted brioche",
        "course": "hot starter",
        "description": "Silky mousse, sour cherry, warm toast.",
        "flavor_profile": "rich, umami, sweet-sour fruit, toasted",
        "price": 22.0,
    },
    {
        "name": "Black truffle risotto, aged parmesan, thyme",
        "course": "pasta",
        "description": "Arborio, black truffle, 36-month parmesan.",
        "flavor_profile": "earthy, savory, creamy, woodland",
        "price": 36.0,
    },
    {
        "name": "Dry-aged ribeye, bone marrow butter, charred alliums",
        "course": "main",
        "description": "45-day ribeye, marrow butter, burnt-onion sweetness.",
        "flavor_profile": "char, mineral, fat, allium, beef",
        "price": 58.0,
    },
    {
        "name": "Dark chocolate, smoked salt, Arbequina olive oil",
        "course": "dessert",
        "description": "72% chocolate, smoke, peppery olive oil.",
        "flavor_profile": "bitter cocoa, smoke, saline, fruit",
        "price": 16.0,
    },
]

PAIRINGS_BY_DISH = {
    "Dungeness crab, yuzu, avocado, cucumber": [
        {
            "category": "wine",
            "name": "Muscadet Sèvre-et-Maine Sur Lie",
            "producer": "Domaine de l'Ecu",
            "region": "Loire, France",
            "style": "Melon de Bourgogne, lees-aged",
            "vintage": "2023",
            "rationale": "High acid and saline lees cut sweet crab and echo yuzu without drowning avocado fat.",
            "price_tier": "$$",
            "glass_price": 16,
            "bottle_price": 62,
        },
        {
            "category": "beer",
            "name": "Kölsch",
            "producer": "Gaffel",
            "region": "Cologne, Germany",
            "style": "pale lager-ale hybrid",
            "vintage": "nv",
            "rationale": "Soft malt and floral hop keep the crab clean; carbonation lifts cucumber.",
            "price_tier": "$",
            "glass_price": 9,
            "bottle_price": 0,
        },
        {
            "category": "spirit",
            "name": "Yuzu highball",
            "producer": "Suntory Toki",
            "region": "Japan",
            "style": "whisky highball, yuzu oleo",
            "vintage": "nv",
            "rationale": "Citrus oil mirrors the dish; dilution and fizz keep ABV polite for a first course.",
            "price_tier": "$$",
            "glass_price": 18,
            "bottle_price": 0,
        },
        {
            "category": "sake",
            "name": "Dassai 45 Junmai Daiginjo",
            "producer": "Asahi Shuzo",
            "region": "Yamaguchi, Japan",
            "style": "fragrant, polished rice",
            "vintage": "nv",
            "rationale": "Melon-and-anise sake sits beside yuzu; umami of crab loves the koji backbone.",
            "price_tier": "$$$",
            "glass_price": 19,
            "bottle_price": 78,
        },
    ],
    "Duck liver mousse, cherry, toasted brioche": [
        {
            "category": "wine",
            "name": "Sauternes",
            "producer": "Château Doisy-Daëne",
            "region": "Bordeaux, France",
            "style": "botrytized Sémillon",
            "vintage": "2018",
            "rationale": "Classic sweet-salt contrast: botrytis honey vs. liver, cherry vs. saffron notes.",
            "price_tier": "$$$",
            "glass_price": 24,
            "bottle_price": 98,
        },
        {
            "category": "beer",
            "name": "Kriek",
            "producer": "Oude Kriek 3 Fonteinen",
            "region": "Flanders, Belgium",
            "style": "lambic with sour cherry",
            "vintage": "2021",
            "rationale": "Cherry and acidity cut the mousse the same way the garnish does.",
            "price_tier": "$$",
            "glass_price": 14,
            "bottle_price": 42,
        },
        {
            "category": "spirit",
            "name": "Bual Madeira, 50ml",
            "producer": "Rare Wine Co. Historic Series",
            "region": "Madeira, Portugal",
            "style": "oxidative, medium-sweet",
            "vintage": "nv",
            "rationale": "Roasted-nut Madeira loves liver; residual sugar handles cherry without cloying.",
            "price_tier": "$$",
            "glass_price": 16,
            "bottle_price": 64,
        },
        {
            "category": "sake",
            "name": "Kamoizumi Nigori Ginjo",
            "producer": "Kamoizumi",
            "region": "Hiroshima, Japan",
            "style": "cloudy, lactic",
            "vintage": "nv",
            "rationale": "Creamy nigori mirrors the mousse; gentle sweetness meets cherry.",
            "price_tier": "$$",
            "glass_price": 15,
            "bottle_price": 58,
        },
    ],
    "Black truffle risotto, aged parmesan, thyme": [
        {
            "category": "wine",
            "name": "Barolo",
            "producer": "G.D. Vajra",
            "region": "Piedmont, Italy",
            "style": "Nebbiolo, tar and rose",
            "vintage": "2019",
            "rationale": "Nebbiolo's tar, rose, and acid stand up to truffle and rinse parmesan fat.",
            "price_tier": "$$$",
            "glass_price": 28,
            "bottle_price": 118,
        },
        {
            "category": "beer",
            "name": "Bière de Garde",
            "producer": "Jenlain Ambrée",
            "region": "Nord, France",
            "style": "cellared amber ale",
            "vintage": "nv",
            "rationale": "Earthy malt and rusticity sit next to woodland truffle without extra hops.",
            "price_tier": "$",
            "glass_price": 10,
            "bottle_price": 0,
        },
        {
            "category": "spirit",
            "name": "White truffle old fashioned",
            "producer": "Rittenhouse Rye",
            "region": "Kentucky, USA",
            "style": "rye, truffle tincture, demerara",
            "vintage": "nv",
            "rationale": "Spice and a drop of truffle tincture extend the risotto's perfume; serve as a 1oz pour.",
            "price_tier": "$$$",
            "glass_price": 22,
            "bottle_price": 0,
        },
        {
            "category": "sake",
            "name": "Tedorigawa Yamahai Junmai",
            "producer": "Yoshida Sake Brewery",
            "region": "Ishikawa, Japan",
            "style": "yamahai, savory",
            "vintage": "nv",
            "rationale": "Lactic, mushroomy yamahai is the closest sake analog to truffle umami.",
            "price_tier": "$$",
            "glass_price": 17,
            "bottle_price": 72,
        },
    ],
    "Dry-aged ribeye, bone marrow butter, charred alliums": [
        {
            "category": "wine",
            "name": "Côte-Rôtie",
            "producer": "Domaine Jamet",
            "region": "Northern Rhône, France",
            "style": "Syrah, smoked meat, violet",
            "vintage": "2018",
            "rationale": "Smoked-meat Syrah is the steak's mirror; tannin and acid cut marrow butter.",
            "price_tier": "$$$$",
            "glass_price": 36,
            "bottle_price": 165,
        },
        {
            "category": "beer",
            "name": "Imperial stout",
            "producer": "North Coast Old Rasputin",
            "region": "California, USA",
            "style": "roasted, full",
            "vintage": "nv",
            "rationale": "Roast and viscosity match char and fat; bitterness stands in for tannin.",
            "price_tier": "$",
            "glass_price": 11,
            "bottle_price": 0,
        },
        {
            "category": "spirit",
            "name": "High West A Midwinter Nights Dram, 30ml",
            "producer": "High West",
            "region": "Utah, USA",
            "style": "rye finished in port barrels",
            "vintage": "Act 11",
            "rationale": "Port-cask rye brings cherry, spice, and oak that love dry-aged beef.",
            "price_tier": "$$$",
            "glass_price": 24,
            "bottle_price": 0,
        },
        {
            "category": "sake",
            "name": "Dewazakura Ichiro Junmai Kimoto",
            "producer": "Dewazakura",
            "region": "Yamagata, Japan",
            "style": "kimoto, structured",
            "vintage": "nv",
            "rationale": "Kimoto grip and grain savor stand up to char without fighting the marrow.",
            "price_tier": "$$",
            "glass_price": 16,
            "bottle_price": 68,
        },
    ],
    "Dark chocolate, smoked salt, Arbequina olive oil": [
        {
            "category": "wine",
            "name": "Banyuls",
            "producer": "Domaine du Mas Blanc",
            "region": "Roussillon, France",
            "style": "vin doux naturel, Grenache",
            "vintage": "2017",
            "rationale": "Oxidative Grenache, cocoa, and salt air are the textbook chocolate pairing.",
            "price_tier": "$$",
            "glass_price": 18,
            "bottle_price": 74,
        },
        {
            "category": "beer",
            "name": "Coffee porter",
            "producer": "Deschutes Black Butte",
            "region": "Oregon, USA",
            "style": "porter",
            "vintage": "nv",
            "rationale": "Roast coffee and chocolate malt double the dessert; low bitterness respects olive oil.",
            "price_tier": "$",
            "glass_price": 9,
            "bottle_price": 0,
        },
        {
            "category": "spirit",
            "name": "Del Maguey Chichicapa, 25ml",
            "producer": "Del Maguey",
            "region": "Oaxaca, Mexico",
            "style": "mezcal espadín",
            "vintage": "nv",
            "rationale": "Smoke matches smoked salt; agave sweetness and olive oil's pepper make a third note.",
            "price_tier": "$$",
            "glass_price": 19,
            "bottle_price": 0,
        },
        {
            "category": "sake",
            "name": "Kikusake Koshu (aged)",
            "producer": "Kikusake",
            "region": "Niigata, Japan",
            "style": "aged sake, caramel",
            "vintage": "2016",
            "rationale": "Caramelized koshu reads as mocha against dark chocolate without extra sugar.",
            "price_tier": "$$$",
            "glass_price": 21,
            "bottle_price": 88,
        },
    ],
}


def _pairings_for(dish_name: str) -> list[dict]:
    if dish_name in PAIRINGS_BY_DISH:
        return [dict(p) for p in PAIRINGS_BY_DISH[dish_name]]
    # Generic but still complete four-category set for unknown dishes.
    return [
        {
            "category": "wine",
            "name": "Village Burgundy, Blanc",
            "producer": "Maison Roche de Bellene",
            "region": "Burgundy, France",
            "style": "Chardonnay",
            "vintage": "2022",
            "rationale": f"Flexible acid and gentle oak sit beside {dish_name} without stealing the plate.",
            "price_tier": "$$",
            "glass_price": 18,
            "bottle_price": 72,
        },
        {
            "category": "beer",
            "name": "Saison",
            "producer": "Saison Dupont",
            "region": "Hainaut, Belgium",
            "style": "farmhouse ale",
            "vintage": "nv",
            "rationale": "Pepper and carbonation reset the palate between bites.",
            "price_tier": "$",
            "glass_price": 10,
            "bottle_price": 0,
        },
        {
            "category": "spirit",
            "name": "Dry sherry, 60ml",
            "producer": "Valdespino Inocente",
            "region": "Jerez, Spain",
            "style": "Fino",
            "vintage": "nv",
            "rationale": "Acetaldehyde lift and saline finish keep service light.",
            "price_tier": "$",
            "glass_price": 12,
            "bottle_price": 48,
        },
        {
            "category": "sake",
            "name": "Hakkaisan Tokubetsu Junmai",
            "producer": "Hakkaisan",
            "region": "Niigata, Japan",
            "style": "clean junmai",
            "vintage": "nv",
            "rationale": "Quiet rice and water let the dish lead; umami still registers.",
            "price_tier": "$$",
            "glass_price": 14,
            "bottle_price": 56,
        },
    ]


def parse_menu_text(text: str, source_name: str = "pasted") -> dict:
    """Parse menu text into dishes. Sample menu maps to rich fixtures; other text is line-parsed."""
    raw = (text or "").strip()
    if not raw:
        dishes = [dict(d) for d in SAMPLE_DISHES]
        return {
            "name": "Maison Madira — Autumn Tasting",
            "cuisine": "California-French",
            "price_tier": "$$$",
            "source_type": source_name,
            "raw_text": SAMPLE_MENU_TEXT,
            "dishes": dishes,
        }

    lowered = raw.lower()
    if "dungeness" in lowered or "maison madira" in lowered or "ribeye" in lowered and "truffle" in lowered:
        return {
            "name": "Maison Madira — Autumn Tasting",
            "cuisine": "California-French",
            "price_tier": "$$$",
            "source_type": source_name,
            "raw_text": raw,
            "dishes": [dict(d) for d in SAMPLE_DISHES],
        }

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
        flavor = _guess_flavor(name)
        dishes.append(
            {
                "name": name,
                "course": course,
                "description": name,
                "flavor_profile": flavor,
                "price": price,
            }
        )
        course = "following"
    if not dishes:
        dishes = [dict(d) for d in SAMPLE_DISHES]
    cuisine = "California-French" if "french" in lowered else "contemporary"
    return {
        "name": source_name or "Uploaded menu",
        "cuisine": cuisine,
        "price_tier": "$$$",
        "source_type": source_name,
        "raw_text": raw,
        "dishes": dishes[:12],
    }


def _guess_flavor(name: str) -> str:
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


def pairings_for_dishes(dishes: list[dict]) -> list[dict]:
    out = []
    for dish in dishes:
        out.append({"dish": dish["name"], "flavor_profile": dish.get("flavor_profile", ""), "pairings": _pairings_for(dish["name"])})
    return out


CURATED_LIST_ITEMS = [
    {"category": "wine", "name": "Muscadet Sèvre-et-Maine Sur Lie", "producer": "Domaine de l'Ecu", "region": "Loire", "style": "Melon, lees", "vintage": "2023", "cost": 18, "pour_price": 16, "bottle_price": 62},
    {"category": "wine", "name": "Chablis Premier Cru Vaillons", "producer": "Jean-Paul & Benoît Droin", "region": "Burgundy", "style": "Chardonnay, steel", "vintage": "2022", "cost": 34, "pour_price": 22, "bottle_price": 96},
    {"category": "wine", "name": "Sancerre", "producer": "François Cotat", "region": "Loire", "style": "Sauvignon Blanc", "vintage": "2023", "cost": 36, "pour_price": 21, "bottle_price": 92},
    {"category": "wine", "name": "Barolo", "producer": "G.D. Vajra", "region": "Piedmont", "style": "Nebbiolo", "vintage": "2019", "cost": 42, "pour_price": 28, "bottle_price": 118},
    {"category": "wine", "name": "Côte-Rôtie", "producer": "Domaine Jamet", "region": "N. Rhône", "style": "Syrah", "vintage": "2018", "cost": 68, "pour_price": 36, "bottle_price": 165},
    {"category": "wine", "name": "Sauternes", "producer": "Doisy-Daëne", "region": "Bordeaux", "style": "botrytis", "vintage": "2018", "cost": 38, "pour_price": 24, "bottle_price": 98},
    {"category": "wine", "name": "Banyuls", "producer": "Mas Blanc", "region": "Roussillon", "style": "VDN Grenache", "vintage": "2017", "cost": 28, "pour_price": 18, "bottle_price": 74},
    {"category": "wine", "name": "Chinon", "producer": "Charles Joguet", "region": "Loire", "style": "Cabernet Franc", "vintage": "2021", "cost": 22, "pour_price": 17, "bottle_price": 68},
    {"category": "beer", "name": "Kölsch", "producer": "Gaffel", "region": "Cologne", "style": "kölsch", "vintage": "nv", "cost": 2.4, "pour_price": 9, "bottle_price": 0},
    {"category": "beer", "name": "Oude Kriek", "producer": "3 Fonteinen", "region": "Flanders", "style": "lambic", "vintage": "2021", "cost": 11, "pour_price": 14, "bottle_price": 42},
    {"category": "beer", "name": "Jenlain Ambrée", "producer": "Duyck", "region": "Nord", "style": "bière de garde", "vintage": "nv", "cost": 3.1, "pour_price": 10, "bottle_price": 0},
    {"category": "beer", "name": "Old Rasputin", "producer": "North Coast", "region": "California", "style": "imperial stout", "vintage": "nv", "cost": 3.4, "pour_price": 11, "bottle_price": 0},
    {"category": "spirit", "name": "Suntory Toki", "producer": "Suntory", "region": "Japan", "style": "blended whisky", "vintage": "nv", "cost": 28, "pour_price": 18, "bottle_price": 0},
    {"category": "spirit", "name": "Rittenhouse Rye", "producer": "Heaven Hill", "region": "Kentucky", "style": "bonded rye", "vintage": "nv", "cost": 22, "pour_price": 16, "bottle_price": 0},
    {"category": "spirit", "name": "Del Maguey Chichicapa", "producer": "Del Maguey", "region": "Oaxaca", "style": "mezcal", "vintage": "nv", "cost": 48, "pour_price": 19, "bottle_price": 0},
    {"category": "spirit", "name": "Valdespino Inocente", "producer": "Valdespino", "region": "Jerez", "style": "Fino", "vintage": "nv", "cost": 18, "pour_price": 12, "bottle_price": 48},
    {"category": "sake", "name": "Dassai 45", "producer": "Asahi Shuzo", "region": "Yamaguchi", "style": "junmai daiginjo", "vintage": "nv", "cost": 32, "pour_price": 19, "bottle_price": 78},
    {"category": "sake", "name": "Tedorigawa Yamahai", "producer": "Yoshida", "region": "Ishikawa", "style": "yamahai junmai", "vintage": "nv", "cost": 29, "pour_price": 17, "bottle_price": 72},
    {"category": "sake", "name": "Dewazakura Ichiro Kimoto", "producer": "Dewazakura", "region": "Yamagata", "style": "kimoto", "vintage": "nv", "cost": 27, "pour_price": 16, "bottle_price": 68},
]


def curate_list(budget: float = 12000, target_margin: float = 3.2) -> dict:
    items = []
    spent = 0.0
    # Assume 12 bottles (or case-equivalent) per wine/sake SKU, 24 for beer, 2 for spirits.
    pack = {"wine": 12, "beer": 24, "spirit": 2, "sake": 12}
    for row in CURATED_LIST_ITEMS:
        qty = pack.get(row["category"], 6)
        line_cost = row["cost"] * qty
        if spent + line_cost > budget * 1.02 and spent > budget * 0.6:
            continue
        pour = row["pour_price"]
        bottle = row["bottle_price"]
        cost = row["cost"]
        if pour:
            margin = round(pour / max(cost / 5, 0.01), 2)  # ~5oz pour from 750
        elif bottle:
            margin = round(bottle / max(cost, 0.01), 2)
        else:
            margin = target_margin
        items.append({**row, "qty": qty, "line_cost": round(line_cost, 2), "margin_pct": round((1 - 1 / max(margin, 0.01)) * 100, 1), "pour_multiple": margin})
        spent += line_cost

    coverage = {}
    for item in items:
        coverage.setdefault(item["category"], {"count": 0, "regions": set(), "styles": set(), "spend": 0.0})
        coverage[item["category"]]["count"] += 1
        coverage[item["category"]]["regions"].add(item["region"])
        coverage[item["category"]]["styles"].add(item["style"])
        coverage[item["category"]]["spend"] += item["line_cost"]
    coverage_out = {
        k: {
            "count": v["count"],
            "regions": sorted(v["regions"]),
            "styles": sorted(v["styles"]),
            "spend": round(v["spend"], 2),
        }
        for k, v in coverage.items()
    }
    expected = {"wine", "beer", "spirit", "sake"}
    gaps = sorted(expected - set(coverage_out))
    if coverage_out.get("wine", {}).get("count", 0) < 6:
        gaps.append("more still wine breadth (need 6+)")
    remaining = round(budget - spent, 2)
    return {
        "name": "Maison Madira autumn list",
        "budget": budget,
        "target_margin": target_margin,
        "spent": round(spent, 2),
        "remaining": remaining,
        "items": items,
        "coverage": coverage_out,
        "gaps": gaps or ["none — categories covered"],
        "notes": f"Buys stay at ${spent:,.0f} of ${budget:,.0f}. Target pour/bottle multiple {target_margin}x.",
    }


LESSONS = [
    {
        "slug": "wine-service",
        "title": "Wine service etiquette",
        "role": "waitstaff",
        "category": "service",
        "body": "Present the bottle with the label facing the host. State producer, grape or appellation, and vintage. Cut the foil below the lip. Wipe. Remove the cork quietly. Pour a one-ounce taste. After approval, pour ladies then host, glasses no more than one-third full for still wine. Never wrap the label. If a guest says the wine is corked, remove it without debate and bring a replacement.",
    },
    {
        "slug": "flavor-talk",
        "title": "Explaining flavor profiles to guests",
        "role": "waitstaff",
        "category": "wine",
        "body": "Lead with structure, not a grocery list: acid, tannin, body, sweetness, alcohol. Then one place and one flavor. 'This Muscadet is lean and salty, like the Loire coast, and it will cut the crab.' Avoid 'notes of pencil shavings' unless the guest asks. Match energy: a celebratory table wants a story; a four-top on a Tuesday wants the short version.",
    },
    {
        "slug": "daily-briefing",
        "title": "Tonight's pairing briefing",
        "role": "all",
        "category": "briefing",
        "body": "Crab → Muscadet or Dassai 45. Mousse → Sauternes or Kriek. Risotto → Barolo or yamahai sake. Ribeye → Côte-Rôtie; imperial stout if they want beer. Chocolate → Banyuls or mezcal. If they order the ribeye and ask 'what's good,' start with Jamet. Upsell the 60ml Madeira with the mousse — it outsells the glass of Sauternes.",
    },
    {
        "slug": "bar-etiquette",
        "title": "Bar and spirit service",
        "role": "bartender",
        "category": "service",
        "body": "Spirit pairings are 25–60ml, never a full cocktail unless ticketed. Announce ABV when pouring mezcal or cask-strength rye. Highballs for the crab course stay under 10% apparent. Never garnish a pairing pour unless the ticket says so. Rinse glassware that previously held oaky wine before sake.",
    },
]

QUIZ = {
    "title": "Floor quiz — autumn pairings",
    "questions": [
        {
            "id": "q1",
            "prompt": "A guest orders the Dungeness crab and wants wine. What do you open first?",
            "choices": ["Côte-Rôtie", "Muscadet Sèvre-et-Maine Sur Lie", "Barolo", "Banyuls"],
            "answer": 1,
            "explain": "Saline, high-acid Muscadet cuts sweet crab and yuzu. Côte-Rôtie is for the ribeye.",
        },
        {
            "id": "q2",
            "prompt": "How full should a still-wine glass be after service?",
            "choices": ["To the brim", "Halfway", "About one-third", "A tasting splash only"],
            "answer": 2,
            "explain": "One-third leaves room for aroma and a second pass.",
        },
        {
            "id": "q3",
            "prompt": "The ribeye guest wants beer, not wine. Best fit?",
            "choices": ["Kölsch", "Kriek", "Imperial stout", "Pilsner"],
            "answer": 2,
            "explain": "Roast and viscosity of imperial stout match char and marrow.",
        },
        {
            "id": "q4",
            "prompt": "A guest says the wine is corked. You should:",
            "choices": [
                "Argue that it smells fine",
                "Remove it without debate and replace it",
                "Ask the sommelier to taste at the table to prove them wrong",
                "Charge a recorking fee",
            ],
            "answer": 1,
            "explain": "Never debate. Replace, then taste in the back.",
        },
    ],
}

ROLEPLAY_OPENER = (
    "You are a diner at Maison Madira. Stay in character. You ordered the dry-aged ribeye "
    "and you are skeptical of sommeliers. Ask what you should drink, push back once on price, "
    "then either accept a pairing or request beer."
)

SUPPLIERS = [
    {"name": "Kermit Lynch Wine Merchant", "kind": "importer", "contact_email": "tastings@kermitlynch.example", "notes": "Loire, Rhône, Burgundy."},
    {"name": "Skurnik Wines", "kind": "importer", "contact_email": "events@skurnik.example", "notes": "Grower Champagne, sake, grower spirits."},
    {"name": "Bay Area Craft Beer Collective", "kind": "distributor", "contact_email": "orders@bacbc.example", "notes": "Draft and bottle beer."},
    {"name": "World Sake Imports", "kind": "importer", "contact_email": "hello@worldsake.example", "notes": "Junmai, yamahai, koshu."},
]

INVENTORY = [
    {"sku": "W-MUS-01", "name": "Muscadet Domaine de l'Ecu", "category": "wine", "supplier": "Kermit Lynch Wine Merchant", "on_hand": 4, "par": 12, "unit_cost": 18, "depletion_30d": 18},
    {"sku": "W-BAR-01", "name": "Barolo G.D. Vajra 2019", "category": "wine", "supplier": "Skurnik Wines", "on_hand": 9, "par": 8, "unit_cost": 42, "depletion_30d": 6},
    {"sku": "W-COT-01", "name": "Côte-Rôtie Jamet 2018", "category": "wine", "supplier": "Kermit Lynch Wine Merchant", "on_hand": 2, "par": 6, "unit_cost": 68, "depletion_30d": 5},
    {"sku": "W-SAU-01", "name": "Sauternes Doisy-Daëne 2018", "category": "wine", "supplier": "Skurnik Wines", "on_hand": 7, "par": 6, "unit_cost": 38, "depletion_30d": 4},
    {"sku": "W-BAN-01", "name": "Banyuls Mas Blanc 2017", "category": "wine", "supplier": "Kermit Lynch Wine Merchant", "on_hand": 3, "par": 8, "unit_cost": 28, "depletion_30d": 9},
    {"sku": "W-CHA-01", "name": "Chablis 1er Vaillons Droin", "category": "wine", "supplier": "Kermit Lynch Wine Merchant", "on_hand": 11, "par": 10, "unit_cost": 34, "depletion_30d": 8},
    {"sku": "B-KOL-01", "name": "Gaffel Kölsch keg", "category": "beer", "supplier": "Bay Area Craft Beer Collective", "on_hand": 1, "par": 2, "unit_cost": 95, "depletion_30d": 3, "unit": "keg"},
    {"sku": "B-KRK-01", "name": "3 Fonteinen Oude Kriek", "category": "beer", "supplier": "Bay Area Craft Beer Collective", "on_hand": 8, "par": 12, "unit_cost": 11, "depletion_30d": 10},
    {"sku": "B-STT-01", "name": "Old Rasputin Imperial Stout", "category": "beer", "supplier": "Bay Area Craft Beer Collective", "on_hand": 14, "par": 12, "unit_cost": 3.4, "depletion_30d": 16},
    {"sku": "S-TOK-01", "name": "Suntory Toki", "category": "spirit", "supplier": "Skurnik Wines", "on_hand": 2, "par": 3, "unit_cost": 28, "depletion_30d": 2},
    {"sku": "S-RYE-01", "name": "Rittenhouse Rye", "category": "spirit", "supplier": "Skurnik Wines", "on_hand": 4, "par": 3, "unit_cost": 22, "depletion_30d": 3},
    {"sku": "S-MEZ-01", "name": "Del Maguey Chichicapa", "category": "spirit", "supplier": "Skurnik Wines", "on_hand": 1, "par": 2, "unit_cost": 48, "depletion_30d": 3},
    {"sku": "K-DAS-01", "name": "Dassai 45 720ml", "category": "sake", "supplier": "World Sake Imports", "on_hand": 5, "par": 10, "unit_cost": 32, "depletion_30d": 11},
    {"sku": "K-YAM-01", "name": "Tedorigawa Yamahai", "category": "sake", "supplier": "World Sake Imports", "on_hand": 6, "par": 6, "unit_cost": 29, "depletion_30d": 4},
    {"sku": "K-KIM-01", "name": "Dewazakura Ichiro Kimoto", "category": "sake", "supplier": "World Sake Imports", "on_hand": 2, "par": 6, "unit_cost": 27, "depletion_30d": 7},
]


def build_ics(title: str, starts_at: str, ends_at: str, location: str, notes: str) -> str:
    def _compact(ts: str) -> str:
        return ts.replace("-", "").replace(":", "").replace(" ", "T")[:15]

    uid = f"{_compact(starts_at)}-madira@maison.local"
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Maison Madira//Madira//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART:{_compact(starts_at)}",
            f"DTEND:{_compact(ends_at)}",
            f"SUMMARY:{title}",
            f"LOCATION:{location}",
            f"DESCRIPTION:{notes} (draft only — not sent)",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
