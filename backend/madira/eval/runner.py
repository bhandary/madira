"""Score menu extraction and stock-grounded pairings.

The labeled menus live in ``fixtures/evals``. Extraction is the same ingest
path the product uses. Pairing imports ``fixtures/sample_list.csv``, stocks
those SKUs, and checks the grid. Demo mode is deterministic. Live mode calls
the model and does not substitute fixture dishes or fixture copy.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

from madira.domain.menu.schemas import normalize

ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "fixtures" / "evals"
LIST_PATH = ROOT / "fixtures" / "sample_list.csv"

RECALL_MIN = 0.90
PRECISION_MIN = 0.90
FIELD_MIN = 0.80
FIELDS = (
    ("name", "name"),
    ("course", "course"),
    ("price", "price"),
    ("main_component", "main component"),
    ("cooking_method", "cooking method"),
    ("sauce", "sauce"),
    ("allergens", "allergens"),
)
_LEVELS = ("richness", "acidity", "sweetness", "spice", "umami", "tannin")
_SLOTS = ("best_by_the_glass", "best_bottle", "value", "adventurous")
_PNG = b"\x89PNG\r\n\x1a\n"


def run(live: bool) -> int:
    if live:
        from madira.tenancy import demo_posture

        if demo_posture():
            print("Live eval refused: the runtime is in demo mode. Fixtures are not used.")
            return 1
        _forbid_fixtures()

    from madira.llm_runtime import resolve_runtime
    from madira.seed import seed
    from madira.tenancy import bind, ensure_demo_tenant, reset

    runtime = resolve_runtime()
    mode = "live" if live else "demo"
    print(f"eval: {mode} ({runtime.provider}:{runtime.model})")
    cases = _cases()
    _require_pngs(cases)
    seed()
    ctx = ensure_demo_tenant()
    token = bind(ctx)
    try:
        listed = _import_list(ctx.venue_id)
        extraction, extract_problems = _score_extraction(ctx.venue_id, cases)
        pairing, pair_problems = _score_pairing(ctx.venue_id, cases, listed)
    finally:
        reset(token)

    _print_extraction(extraction)
    _print_pairing(pairing)
    problems = extract_problems + pair_problems + _threshold_problems(extraction, pairing)
    if problems:
        print("result: fail")
        for line in problems:
            print(f"  {line}")
        return 1
    print("result: pass")
    return 0


def _forbid_fixtures() -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("live eval must not fall back to fixtures")

    import madira.agents.demo.menu as demo_menu
    import madira.domain.menu.extract as extract
    import madira.domain.pairing.copy as copy

    demo_menu.extraction_json = boom
    demo_menu.known_payloads = boom
    extract.demo_complete = boom
    copy.demo_lines = boom


def _cases() -> list[dict]:
    found = []
    for path in sorted(LABELS.glob("*.json")):
        case = json.loads(path.read_text())
        case["id"] = case.get("id") or path.stem
        if case.get("pairing", {}).get("list") != "fixtures/sample_list.csv":
            raise SystemExit(f"{path.name} must pair against fixtures/sample_list.csv")
        found.append(case)
    if len(found) < 2:
        raise SystemExit("the eval set needs more than one labeled menu")
    return found


def _require_pngs(cases: list[dict]) -> None:
    for case in cases:
        for rel in case["files"]:
            path = ROOT / rel
            if path.suffix.lower() == ".png":
                _decodable_png(path)


def _decodable_png(path: Path) -> None:
    data = path.read_bytes()
    if not data.startswith(_PNG) or len(data) >= 500_000:
        raise SystemExit(f"{path} is not a small decodable PNG")
    pos = 8
    idat = bytearray()
    saw_end = False
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > len(data):
            raise SystemExit(f"{path} is not a decodable PNG")
        if kind == b"IDAT":
            idat.extend(data[start:end])
        if kind == b"IHDR" and length >= 8:
            width = int.from_bytes(data[start : start + 4], "big")
            height = int.from_bytes(data[start + 4 : start + 8], "big")
            if width < 1 or height < 1:
                raise SystemExit(f"{path} is not a decodable PNG")
        pos = end + 4
        if kind == b"IEND":
            saw_end = True
            break
    if not saw_end or not idat:
        raise SystemExit(f"{path} is not a decodable PNG")
    try:
        zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise SystemExit(f"{path} is not a decodable PNG") from exc


def _import_list(venue_id) -> set:
    from madira.domain.lists.csv_import import import_csv

    import_csv(
        venue_id,
        filename="sample_list.csv",
        body=LIST_PATH.read_bytes(),
        content_type="text/csv",
        confirm=True,
    )
    return _stock(venue_id)


def _stock(venue_id) -> set:
    from sqlalchemy import select

    from madira.db import SessionLocal
    from madira.models import InventoryItem, ListItem

    session = SessionLocal()
    try:
        sku_ids = set(
            session.scalars(select(ListItem.sku_id).where(ListItem.venue_id == venue_id)).all()
        )
        for sku_id in sku_ids:
            rows = session.scalars(
                select(InventoryItem).where(
                    InventoryItem.venue_id == venue_id,
                    InventoryItem.sku_id == sku_id,
                )
            ).all()
            if not rows:
                session.add(InventoryItem(venue_id=venue_id, sku_id=sku_id, on_hand=6, unit="btl"))
            elif sum(int(row.on_hand or 0) for row in rows) <= 0:
                rows[0].on_hand = 6
        session.commit()
        return sku_ids
    finally:
        session.close()


def _score_extraction(venue_id, cases: list[dict]) -> tuple[dict, list[str]]:
    from madira.domain.errors import DraftFailed
    from madira.domain.menu.service import ingest_menu

    totals = {"gold": 0, "predicted": 0, "matched": 0}
    hits = {key: 0 for key, _label in FIELDS}
    problems: list[str] = []
    print("extraction")
    for case in cases:
        gold = case["dishes"]
        for rel in case["files"]:
            path = ROOT / rel
            try:
                review = ingest_menu(
                    venue_id,
                    filename=path.name,
                    body=path.read_bytes(),
                    content_type=_media(path),
                )
                predicted = review["dishes"]
            except DraftFailed as exc:
                predicted = []
                problems.append(f"{case['id']} {path.name}: {exc.message}")
            except RuntimeError as exc:
                if "must not fall back" in str(exc):
                    raise
                predicted = []
                problems.append(f"{case['id']} {path.name}: {exc}")
            matched = _align(gold, predicted)
            file_hits = _field_hits(matched)
            totals["gold"] += len(gold)
            totals["predicted"] += len(predicted)
            totals["matched"] += len(matched)
            for key, _label in FIELDS:
                hits[key] += file_hits[key]
            recall = _rate(len(matched), len(gold))
            precision = _rate(len(matched), len(predicted))
            print(f"  {case['id']} {path.name}  recall={recall:.3f}  precision={precision:.3f}")
    totals["hits"] = hits
    return totals, problems


def _score_pairing(venue_id, cases: list[dict], listed: set) -> tuple[dict, list[str]]:
    from madira.domain.errors import DraftFailed
    from madira.domain.menu.service import confirm_version, ingest_menu
    from madira.domain.pairing.service import pin, recommend, reject

    counts = {
        "dishes": 0,
        "slot_dishes": 0,
        "suggestions": 0,
        "on_list": 0,
        "in_stock": 0,
        "profile": 0,
        "profile_pass": 0,
        "pins": 0,
        "pins_pass": 0,
        "rejects": 0,
        "rejects_pass": 0,
    }
    problems: list[str] = []
    on_hand = _on_hand(venue_id)
    print("pairing")
    for case in cases:
        path = ROOT / case["pair_file"]
        try:
            review = ingest_menu(
                venue_id,
                filename=path.name,
                body=path.read_bytes(),
                content_type=_media(path),
            )
            confirm_version(venue_id, review["menu_id"], review["version_id"])
            paired = recommend(venue_id, review["menu_id"])
        except DraftFailed as exc:
            problems.append(f"{case['id']} pairing: {exc.message}")
            print(f"  {case['id']} {path.name}  failed")
            continue
        if paired.get("error"):
            problems.append(f"{case['id']} pairing: {paired['error']}")
            print(f"  {case['id']} {path.name}  failed")
            continue
        by_name = {normalize(dish["name"]): dish for dish in paired["dishes"]}
        menu_suggestions = 0
        menu_gaps = 0
        for gold in case["dishes"]:
            counts["dishes"] += 1
            dish = by_name.get(normalize(gold["name"]))
            if dish is None:
                problems.append(f"{case['id']} pairing missing {gold['name']}")
                continue
            rows = list(dish["pairings"])
            slots = [row.get("slot") for row in rows]
            if len(rows) == len(_SLOTS) and set(slots) == set(_SLOTS) and _slots_explicit(rows):
                counts["slot_dishes"] += 1
            else:
                problems.append(f"{case['id']} {gold['name']} does not have four slots or an explicit gap")
            for row in rows:
                if row.get("status") == "gap" or not row.get("sku_id"):
                    if row.get("status") == "gap":
                        menu_gaps += 1
                    continue
                counts["suggestions"] += 1
                menu_suggestions += 1
                sku_id = row["sku_id"]
                if sku_id in listed:
                    counts["on_list"] += 1
                else:
                    problems.append(f"{case['id']} {gold['name']} {row.get('slot')} is not on the imported list")
                if on_hand.get(sku_id, 0) > 0:
                    counts["in_stock"] += 1
                else:
                    problems.append(f"{case['id']} {gold['name']} {row.get('slot')} is not in stock")
            _profile_checks(case, gold, rows, counts, problems)
        if case["pairing"].get("pins") or case["pairing"].get("rejects"):
            _pin_and_reject(venue_id, review["menu_id"], paired, case, counts, problems, pin, reject, recommend)
        print(f"  {case['id']} {path.name}  suggestions={menu_suggestions}  gaps={menu_gaps}")
    return counts, problems


def _slots_explicit(rows: list[dict]) -> bool:
    for row in rows:
        if row.get("status") == "gap":
            if row.get("sku_id") or not str(row.get("gap") or "").strip():
                return False
            continue
        if not row.get("sku_id"):
            return False
    return True


def _profile_checks(case: dict, gold: dict, rows: list[dict], counts: dict, problems: list[str]) -> None:
    dish_levels = {name: int(gold.get(name) or 0) for name in _LEVELS}
    for rule in case["pairing"].get("rules") or []:
        if not _fits(rule.get("when") or {}, dish_levels):
            continue
        counts["profile"] += 1
        violated = False
        for row in rows:
            if row.get("status") == "gap" or not row.get("sku_id"):
                continue
            profile = _drink_values(row["sku_id"])
            if _fits(rule.get("drink") or {}, profile):
                violated = True
                problems.append(
                    f"{case['id']} {gold['name']} {row.get('slot')}: {rule.get('reason') or 'profile fit'}"
                )
        if not violated:
            counts["profile_pass"] += 1


def _pin_and_reject(venue_id, menu_id, paired: dict, case: dict, counts: dict, problems: list[str], pin, reject, recommend) -> None:
    dish = next(
        (
            row
            for row in paired["dishes"]
            if sum(1 for item in row["pairings"] if item.get("sku_id") and item.get("status") != "gap") >= 2
        ),
        None,
    )
    if dish is None:
        problems.append(f"{case['id']} has no dish with two bottles to pin and reject")
        return
    chosen = [row for row in dish["pairings"] if row.get("sku_id") and row.get("status") != "gap"]
    held, refused = chosen[0], chosen[1]
    try:
        if case["pairing"].get("pins"):
            counts["pins"] += 1
            pin(venue_id, menu_id, held["id"])
        if case["pairing"].get("rejects"):
            counts["rejects"] += 1
            reject(venue_id, menu_id, refused["id"])
        again = recommend(venue_id, menu_id)
    except Exception as exc:
        message = getattr(exc, "message", None) or str(exc)
        if "must not fall back" in message:
            raise
        problems.append(f"{case['id']} pin/reject: {message}")
        return
    if again.get("error"):
        problems.append(f"{case['id']} re-pair: {again['error']}")
        return
    fresh = next(row for row in again["dishes"] if row["name"] == dish["name"])
    if case["pairing"].get("pins"):
        pinned = next(row for row in fresh["pairings"] if row["slot"] == held["slot"])
        if pinned.get("status") == "pinned" and str(pinned.get("sku_id")) == str(held["sku_id"]):
            counts["pins_pass"] += 1
        else:
            problems.append(f"{case['id']} pin on {dish['name']} was not kept")
    if case["pairing"].get("rejects"):
        if any(str(row.get("sku_id")) == str(refused["sku_id"]) for row in fresh["pairings"]):
            problems.append(f"{case['id']} rejected bottle on {dish['name']} was suggested again")
        else:
            counts["rejects_pass"] += 1


def _drink_values(sku_id) -> dict:
    from sqlalchemy import select

    from madira.db import SessionLocal
    from madira.domain.pairing.profiles import derive_profile
    from madira.models import Sku, TastingNote

    session = SessionLocal()
    try:
        sku = session.get(Sku, sku_id)
        product = sku.variant.product
        note = session.scalar(
            select(TastingNote)
            .where(
                TastingNote.venue_id == sku.venue_id,
                TastingNote.product_id == product.id,
                TastingNote.status == "approved",
            )
            .order_by(TastingNote.approved_at.desc(), TastingNote.id.desc())
        )
        profile = derive_profile(product, note)
    finally:
        session.close()
    return {name: int(getattr(profile, name)) for name in _LEVELS}


def _fits(spec: dict, values: dict) -> bool:
    for key, bound in spec.items():
        if key.endswith("_gte"):
            field = key[: -len("_gte")]
        elif key.endswith("_lte"):
            field = key[: -len("_lte")]
        else:
            raise SystemExit(f"unknown pairing constraint {key}")
        if field not in _LEVELS:
            raise SystemExit(f"unknown pairing field {field}")
        number = int(values.get(field, 0))
        if key.endswith("_gte") and number < int(bound):
            return False
        if key.endswith("_lte") and number > int(bound):
            return False
    return True


def _on_hand(venue_id) -> dict:
    from sqlalchemy import select

    from madira.db import SessionLocal
    from madira.models import InventoryItem

    session = SessionLocal()
    try:
        found: dict = {}
        rows = session.scalars(select(InventoryItem).where(InventoryItem.venue_id == venue_id)).all()
        for row in rows:
            found[row.sku_id] = found.get(row.sku_id, 0) + int(row.on_hand or 0)
        return found
    finally:
        session.close()


def _align(gold: list[dict], predicted: list[dict]) -> list[tuple[dict, dict]]:
    remaining = list(predicted)
    pairs = []
    for dish in gold:
        key = normalize(dish["name"])
        index = next((i for i, row in enumerate(remaining) if normalize(row["name"]) == key), None)
        if index is None:
            continue
        pairs.append((dish, remaining.pop(index)))
    return pairs


def _field_hits(pairs: list[tuple[dict, dict]]) -> dict[str, int]:
    hits = {key: 0 for key, _label in FIELDS}
    for gold, pred in pairs:
        for key, _label in FIELDS:
            if _same(key, gold, pred):
                hits[key] += 1
    return hits


def _same(key: str, gold: dict, pred: dict) -> bool:
    if key == "price":
        return int(gold.get("price") or 0) == int(pred.get("price") or 0)
    if key == "allergens":
        return _names(gold.get("allergens")) == _names(pred.get("allergens"))
    return normalize(str(gold.get(key) or "")) == normalize(str(pred.get(key) or ""))


def _names(values) -> set[str]:
    return {normalize(str(item)) for item in (values or []) if normalize(str(item))}


def _rate(hit: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return hit / total


def _print_extraction(totals: dict) -> None:
    recall = _rate(totals["matched"], totals["gold"])
    precision = _rate(totals["matched"], totals["predicted"])
    print(
        f"extraction summary  files_scored  gold={totals['gold']}  "
        f"predicted={totals['predicted']}  matched={totals['matched']}"
    )
    print(f"  recall={recall:.3f} (min {RECALL_MIN:.2f})  precision={precision:.3f} (min {PRECISION_MIN:.2f})")
    for key, label in FIELDS:
        accuracy = _rate(totals["hits"][key], totals["matched"])
        print(f"  {label}={accuracy:.3f} (min {FIELD_MIN:.2f})")


def _print_pairing(counts: dict) -> None:
    print(
        "pairing summary  "
        f"dishes={counts['dishes']}  "
        f"four slots or gap={counts['slot_dishes']}/{counts['dishes']}  "
        f"on list={counts['on_list']}/{counts['suggestions']}  "
        f"in stock={counts['in_stock']}/{counts['suggestions']}"
    )
    print(
        f"  pins={counts['pins_pass']}/{counts['pins']}  "
        f"rejects={counts['rejects_pass']}/{counts['rejects']}  "
        f"profile={counts['profile_pass']}/{counts['profile']}"
    )


def _threshold_problems(extraction: dict, pairing: dict) -> list[str]:
    problems = []
    recall = _rate(extraction["matched"], extraction["gold"])
    precision = _rate(extraction["matched"], extraction["predicted"])
    if recall < RECALL_MIN:
        problems.append(f"dish recall {recall:.3f} is below {RECALL_MIN:.2f}")
    if precision < PRECISION_MIN:
        problems.append(f"dish precision {precision:.3f} is below {PRECISION_MIN:.2f}")
    for key, label in FIELDS:
        accuracy = _rate(extraction["hits"][key], extraction["matched"])
        if accuracy < FIELD_MIN:
            problems.append(f"{label} accuracy {accuracy:.3f} is below {FIELD_MIN:.2f}")
    if pairing["slot_dishes"] != pairing["dishes"]:
        problems.append("a dish is missing four slots or an explicit gap")
    if pairing["suggestions"] == 0 or pairing["on_list"] != pairing["suggestions"]:
        problems.append("a suggested SKU is not on the imported list")
    if pairing["in_stock"] != pairing["suggestions"]:
        problems.append("a suggested SKU is not in stock")
    if pairing["pins"] == 0 or pairing["pins_pass"] != pairing["pins"]:
        problems.append("a pin was not kept")
    if pairing["rejects"] == 0 or pairing["rejects_pass"] != pairing["rejects"]:
        problems.append("a reject was not honored")
    if pairing["profile"] == 0 or pairing["profile_pass"] != pairing["profile"]:
        problems.append("a profile-fit check failed")
    return problems


def _media(path: Path) -> str:
    return {".png": "image/png", ".pdf": "application/pdf", ".txt": "text/plain"}[path.suffix.lower()]
