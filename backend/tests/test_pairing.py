"""Pairings come from the venue's list. Pins, swaps, and rejections stick."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from madira.auth import SESSION_COOKIE, issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.catalog.service import ensure_sku
from madira.domain.pairing.copy import set_pairing_completer
from madira.main import app
from madira.models import BeverageList, Dish, InventoryItem, ListItem, Membership, Pairing, User, Venue
from madira.seed import seed
from madira.tenancy import AUDITOR, DEMO_USER_SUB, MANAGER, OWNER, SOMMELIER, STAFF, ensure_demo_tenant

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
AUTH_SECRET = "pairing-test-secret"
SLOTS = ["best_by_the_glass", "best_bottle", "value", "adventurous"]
OCTOPUS = "Grilled octopus, chili, olive oil — $24\nLemon tart — $12\n"
OCTOPUS_EDITED = "Grilled octopus, chili, olive oil — $30\nLemon tart — $12\n"
LIST_CSV = (
    "section,name,producer,vintage,region,country,category,style,grape,bottle size,bottle price,glass price,cost,barcode\n"
    "White,House Muscadet,Domaine Test,2022,Loire,France,wine,Melon,Melon,750ml,62,16,18,P-MUS\n"
    "Red,House Barolo,Vajra Test,2019,Piedmont,Italy,wine,Nebbiolo,Nebbiolo,750ml,118,28,42,P-BAR\n"
    "Beer,House Kolsch,Gaffel Test,,Cologne,Germany,beer,Kolsch,,500ml,,9,2,P-KOL\n"
    "Sake,House Dassai,Asahi Test,,Yamaguchi,Japan,sake,Junmai Daiginjo,,720ml,78,19,32,P-DAS\n"
)


@pytest.fixture(autouse=True)
def _reset_completer():
    set_pairing_completer(None)
    yield
    set_pairing_completer(None)


@pytest.fixture
def client():
    init_db()
    seed()
    with TestClient(app) as test_client:
        yield test_client


def _as(client: TestClient, monkeypatch, google_sub: str) -> None:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    client.cookies.set(SESSION_COOKIE, issue_session(google_sub))


def _member(session, google_sub: str, email: str, venue_id, role: str) -> User:
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id))
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role
    return user


def _venue(slug: str) -> Venue:
    session = SessionLocal()
    try:
        demo = ensure_demo_tenant(session)
        venue = session.scalar(select(Venue).where(Venue.slug == slug))
        if venue is None:
            venue = Venue(organization_id=demo.organization_id, name=slug, slug=slug)
            session.add(venue)
            session.flush()
        _member(session, f"owner-{slug}", f"owner-{slug}@example.com", venue.id, OWNER)
        session.commit()
        session.refresh(venue)
        return venue
    finally:
        session.close()


def _sign_in(client, monkeypatch, slug: str) -> Venue:
    venue = _venue(slug)
    _as(client, monkeypatch, f"owner-{slug}")
    return venue


def _import_list(client: TestClient, csv_text: str = LIST_CSV) -> None:
    response = client.post(
        "/lists/import",
        files={"file": ("list.csv", csv_text, "text/csv")},
        data={"confirm": "true"},
    )
    assert response.status_code == 200, response.text


def _menu(client: TestClient, text: str, menu_id: str = "") -> dict:
    data = {"text": text}
    if menu_id:
        data["menu_id"] = menu_id
    response = client.post("/menus/ingest", data=data)
    assert response.status_code == 200, response.text
    review = response.json()["review"]
    if review["status"] != "confirmed":
        confirmed = client.post(f"/menus/{review['menu_id']}/versions/{review['version_id']}/confirm")
        assert confirmed.status_code == 200, confirmed.text
        review = confirmed.json()["review"]
    return review


def _pair(client: TestClient, menu_id: str):
    return client.post(f"/menus/{menu_id}/pair")


def _slots(body: dict, dish_name: str = "") -> list[dict]:
    dishes = body["dishes"]
    if dish_name:
        dishes = [dish for dish in dishes if dish["name"].startswith(dish_name)]
    return dishes[0]["pairings"]


def _sku_ids(rows: list[dict]) -> list[str]:
    return [str(row["sku_id"]) for row in rows if row.get("sku_id")]


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_sample_list_fills_four_slots(client, monkeypatch):
    _sign_in(client, monkeypatch, _slug("pairing-sample"))
    csv_text = (FIXTURES / "sample_list.csv").read_text()
    menu_text = (FIXTURES / "sample_menu.txt").read_text()
    _import_list(client, csv_text)
    review = _menu(client, menu_text)
    paired = _pair(client, review["menu_id"])
    assert paired.status_code == 200, paired.text
    rows = _slots(paired.json(), "Dungeness")
    assert [row["slot"] for row in rows] == SLOTS
    assert all(row["status"] != "gap" for row in rows)
    assert len(set(_sku_ids(rows))) == 4


def test_only_listed_in_stock_bottles_are_suggested_and_gaps_name_the_hole(client, monkeypatch):
    venue = _sign_in(client, monkeypatch, _slug("pairing-stock"))
    review = _menu(client, OCTOPUS)
    bare = _pair(client, review["menu_id"])
    assert bare.status_code == 200, bare.text
    gaps = _slots(bare.json(), "Grilled octopus")
    assert [row["status"] for row in gaps] == ["gap", "gap", "gap", "gap"]
    assert all("Missing" in row["gap"] for row in gaps)
    assert "by the glass" in gaps[0]["gap"]

    session = SessionLocal()
    try:
        listed = ensure_sku(session, venue.id, category="wine", name="Listed Bright", producer="House")
        unlisted = ensure_sku(session, venue.id, category="wine", name="Unlisted Cellar Bottle", producer="House")
        sold_out = ensure_sku(session, venue.id, category="wine", name="Sold Out Chablis", producer="House")
        bottle_only = ensure_sku(session, venue.id, category="wine", name="Bottle Only Barolo", producer="House")
        beverage = BeverageList(venue_id=venue.id, name="Stock list", currency="USD")
        session.add(beverage)
        session.flush()
        session.add_all(
            [
                ListItem(
                    venue_id=venue.id,
                    list_id=beverage.id,
                    sku_id=listed.id,
                    pour_price=1600,
                    bottle_price=6200,
                    currency="USD",
                ),
                ListItem(
                    venue_id=venue.id,
                    list_id=beverage.id,
                    sku_id=sold_out.id,
                    pour_price=1800,
                    bottle_price=7000,
                    currency="USD",
                ),
                ListItem(
                    venue_id=venue.id,
                    list_id=beverage.id,
                    sku_id=bottle_only.id,
                    pour_price=0,
                    bottle_price=9000,
                    currency="USD",
                ),
            ]
        )
        session.add_all(
            [
                InventoryItem(venue_id=venue.id, sku_id=unlisted.id, on_hand=8, unit="btl"),
                InventoryItem(venue_id=venue.id, sku_id=sold_out.id, on_hand=0, unit="btl"),
                InventoryItem(venue_id=venue.id, sku_id=listed.id, on_hand=3, unit="btl"),
            ]
        )
        session.commit()
    finally:
        session.close()

    paired = _pair(client, review["menu_id"])
    assert paired.status_code == 200, paired.text
    blob = paired.text
    assert "Unlisted Cellar Bottle" not in blob
    assert "Sold Out Chablis" not in blob
    assert "Listed Bright" in blob
    rows = _slots(paired.json(), "Grilled octopus")
    assert [row["slot"] for row in rows] == SLOTS
    glass = rows[0]
    assert glass["slot"] == "best_by_the_glass"
    assert glass["status"] != "gap"
    assert glass["glass_price"] == 1600

    session = SessionLocal()
    try:
        only = ensure_sku(session, venue.id, category="wine", name="Cellar Bottle Only", producer="House")
        beverage = BeverageList(venue_id=venue.id, name="Bottle list", currency="USD")
        session.add(beverage)
        session.flush()
        session.add(
            ListItem(
                venue_id=venue.id,
                list_id=beverage.id,
                sku_id=only.id,
                pour_price=0,
                bottle_price=6400,
                currency="USD",
            )
        )
        session.commit()
        only_id = only.id
    finally:
        session.close()
    # A later list still includes the earlier rows. Build a venue whose only
    # listed price is a bottle by zeroing the glass prices, then re-pair.
    session = SessionLocal()
    try:
        session.execute(update(ListItem).where(ListItem.venue_id == venue.id).values(pour_price=0))
        session.commit()
    finally:
        session.close()
    again = _pair(client, review["menu_id"])
    assert again.status_code == 200, again.text
    glass = _slots(again.json(), "Grilled octopus")[0]
    assert glass["status"] == "gap"
    assert "by the glass" in glass["gap"]
    assert str(only_id) in _sku_ids(_slots(again.json(), "Grilled octopus")) or "Cellar Bottle Only" in again.text


def test_structured_profile_picks_the_bottle_and_stock_removes_it(client, monkeypatch):
    venue = _sign_in(client, monkeypatch, _slug("pairing-profile"))
    session = SessionLocal()
    try:
        bright = ensure_sku(
            session,
            venue.id,
            category="wine",
            name="Bright",
            producer="House",
            body="light",
            acidity="high",
            sweetness="dry",
            tannin="none",
        )
        heavy = ensure_sku(
            session,
            venue.id,
            category="wine",
            name="Heavy",
            producer="House",
            body="full",
            acidity="low",
            sweetness="sweet",
            tannin="high",
        )
        beverage = BeverageList(venue_id=venue.id, name="Profile list", currency="USD")
        session.add(beverage)
        session.flush()
        for sku, glass, bottle in ((bright, 1500, 6000), (heavy, 2200, 11000)):
            session.add(
                ListItem(
                    venue_id=venue.id,
                    list_id=beverage.id,
                    sku_id=sku.id,
                    pour_price=glass,
                    bottle_price=bottle,
                    currency="USD",
                )
            )
        session.commit()
        bright_id = bright.id
    finally:
        session.close()
    review = _menu(client, "Oysters, lemon — $18\n")
    session = SessionLocal()
    try:
        session.execute(
            update(Dish)
            .where(Dish.menu_id == uuid.UUID(review["menu_id"]))
            .values(
                richness=1,
                acidity=5,
                sweetness=0,
                spice=0,
                umami=2,
                main_component="oyster",
                sauce="lemon",
                needs_repairing=True,
            )
        )
        session.commit()
    finally:
        session.close()
    paired = _pair(client, review["menu_id"])
    assert paired.status_code == 200, paired.text
    glass = _slots(paired.json())[0]
    assert glass["name"] == "Bright"
    assert glass["sku_id"] == str(bright_id) or str(glass["sku_id"]) == str(bright_id)

    session = SessionLocal()
    try:
        session.add(InventoryItem(venue_id=venue.id, sku_id=bright_id, on_hand=0, unit="btl"))
        session.commit()
    finally:
        session.close()
    repaired = _pair(client, review["menu_id"])
    assert repaired.status_code == 200, repaired.text
    assert "Bright" not in repaired.text
    assert _slots(repaired.json())[0]["name"] == "Heavy"


def test_only_flagged_dishes_are_repaired(client, monkeypatch):
    _sign_in(client, monkeypatch, _slug("pairing-flag"))
    _import_list(client)
    first = _menu(client, OCTOPUS)
    paired = _pair(client, first["menu_id"])
    assert paired.status_code == 200, paired.text
    lemon = next(dish for dish in paired.json()["dishes"] if dish["name"] == "Lemon tart")
    session = SessionLocal()
    try:
        session.execute(
            update(Pairing).where(Pairing.dish_id == uuid.UUID(lemon["id"])).values(rationale="KEEP-ME")
        )
        session.commit()
    finally:
        session.close()
    _menu(client, OCTOPUS_EDITED, first["menu_id"])
    again = _pair(client, first["menu_id"])
    assert again.status_code == 200, again.text
    body = again.json()
    kept = next(dish for dish in body["dishes"] if dish["name"] == "Lemon tart")
    changed = next(dish for dish in body["dishes"] if dish["name"].startswith("Grilled octopus"))
    assert any(row["rationale"] == "KEEP-ME" for row in kept["pairings"])
    assert all("KEEP-ME" not in row["rationale"] for row in changed["pairings"])
    assert changed["needs_repairing"] is True
    assert kept["needs_repairing"] is False


def test_pin_swap_and_reject_persist_and_are_respected(client, monkeypatch):
    _sign_in(client, monkeypatch, _slug("pairing-actions"))
    _import_list(client)
    review = _menu(client, OCTOPUS)
    paired = _pair(client, review["menu_id"])
    assert paired.status_code == 200, paired.text
    dish = next(row for row in paired.json()["dishes"] if row["name"].startswith("Grilled octopus"))
    by_slot = {row["slot"]: row for row in dish["pairings"]}
    pinned = by_slot["best_by_the_glass"]
    swapped = by_slot["best_bottle"]
    rejected = by_slot["value"]
    assert pinned["sku_id"] and swapped["sku_id"] and rejected["sku_id"]

    held = client.post(f"/menus/{review['menu_id']}/pairings/{pinned['id']}/pin")
    assert held.status_code == 200, held.text
    pinned_row = next(
        row
        for row in _slots(held.json(), "Grilled octopus")
        if row["slot"] == "best_by_the_glass"
    )
    assert pinned_row["status"] == "pinned"
    assert pinned_row["sku_id"] == pinned["sku_id"]
    reread = client.get(f"/menus/{review['menu_id']}/pairings")
    assert reread.status_code == 200
    assert next(row["status"] for row in _slots(reread.json(), "Grilled octopus") if row["slot"] == "best_by_the_glass") == "pinned"

    taken = {pinned["sku_id"], swapped["sku_id"], rejected["sku_id"]}
    other = next(option for option in dish["options"] if option["sku_id"] not in taken)
    moved = client.post(
        f"/menus/{review['menu_id']}/pairings/{swapped['id']}/swap",
        json={"sku_id": other["sku_id"]},
    )
    assert moved.status_code == 200, moved.text
    moved_row = next(row for row in _slots(moved.json(), "Grilled octopus") if row["slot"] == "best_bottle")
    assert moved_row["status"] == "swapped"
    assert moved_row["sku_id"] == other["sku_id"]
    assert moved_row["name"] != swapped["name"]

    refused = client.post(f"/menus/{review['menu_id']}/pairings/{rejected['id']}/reject")
    assert refused.status_code == 200, refused.text
    refused_row = next(row for row in _slots(refused.json(), "Grilled octopus") if row["slot"] == "value")
    assert refused_row["status"] == "rejected"
    assert refused_row["sku_id"] == rejected["sku_id"]

    again = _pair(client, review["menu_id"])
    assert again.status_code == 200, again.text
    fresh = {row["slot"]: row for row in _slots(again.json(), "Grilled octopus")}
    assert fresh["best_by_the_glass"]["status"] == "pinned"
    assert fresh["best_by_the_glass"]["sku_id"] == pinned["sku_id"]
    assert fresh["best_bottle"]["status"] == "swapped"
    assert fresh["best_bottle"]["sku_id"] == other["sku_id"]
    assert rejected["sku_id"] not in _sku_ids(list(fresh.values()))


def test_invented_sku_is_rejected_and_a_schema_miss_retries_once(client, monkeypatch):
    copy_venue = _sign_in(client, monkeypatch, _slug("pairing-copy"))
    _import_list(client)
    review = _menu(client, OCTOPUS)
    invented = str(uuid.uuid4())

    def bad(prompt: str) -> str:
        candidates = []
        for line in prompt.splitlines():
            if line.startswith("CANDIDATES_JSON="):
                candidates = json.loads(line.split("=", 1)[1])
        return json.dumps(
            {
                "slots": [
                    {
                        "slot": row["slot"],
                        "sku_id": invented,
                        "rationale": "This rationale is long enough to pass the check.",
                        "server_script": "Offer this bottle.",
                    }
                    for row in candidates
                ]
            }
        )

    set_pairing_completer(bad)
    failed = _pair(client, review["menu_id"])
    assert failed.status_code == 422
    assert failed.json()["detail"] == "The pairing copy named a SKU that is not a candidate."
    assert invented not in failed.text
    session = SessionLocal()
    try:
        stored = session.scalars(select(Pairing).where(Pairing.venue_id == copy_venue.id)).all()
        assert all(str(row.sku_id) != invented for row in stored)
        assert stored == []
    finally:
        session.close()

    calls: list[str] = []

    def flaky(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "{"
        candidates = []
        for line in prompt.splitlines():
            if line.startswith("CANDIDATES_JSON="):
                candidates = json.loads(line.split("=", 1)[1])
        return json.dumps(
            {
                "slots": [
                    {
                        "slot": row["slot"],
                        "sku_id": row["sku_id"],
                        "rationale": "Acid and weight line up with the dish.",
                        "server_script": "Offer this bottle with the dish.",
                    }
                    for row in candidates
                ]
            }
        )

    solo = _menu(client, "Grilled octopus, chili, olive oil — $24\n")
    set_pairing_completer(flaky)
    repaired = _pair(client, solo["menu_id"])
    assert repaired.status_code == 200, repaired.text
    assert len(calls) == 2
    assert "Acid and weight" in repaired.text

    calls.clear()

    def invalid(_prompt: str) -> str:
        calls.append("x")
        return "nope"

    set_pairing_completer(invalid)
    # The dish is already paired, so a second run still asks for copy when the
    # slot is suggested. Force every choice to need copy by using a new menu.
    other = _menu(client, "Crab toast — $16\n")
    missed = _pair(client, other["menu_id"])
    assert missed.status_code == 422
    assert missed.json()["detail"] == "The pairing copy did not match the schema after one retry."
    assert len(calls) == 2


def test_live_copy_uses_the_model_and_reports_a_failure(client, monkeypatch):
    _sign_in(client, monkeypatch, _slug("pairing-live"))
    _import_list(client)
    review = _menu(client, OCTOPUS)
    other = _menu(client, "Crab toast — $16\n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-pairing")

    def model(prompt: str) -> str:
        candidates = []
        for line in prompt.splitlines():
            if line.startswith("CANDIDATES_JSON="):
                candidates = json.loads(line.split("=", 1)[1])
        return json.dumps(
            {
                "slots": [
                    {
                        "slot": row["slot"],
                        "sku_id": row["sku_id"],
                        "rationale": "The model wrote this pairing rationale.",
                        "server_script": "The model wrote this script.",
                    }
                    for row in candidates
                ]
            }
        )

    def demo_boom(*_args, **_kwargs):
        raise AssertionError("demo copy")

    monkeypatch.setattr("madira.domain.pairing.copy.live_complete", model)
    monkeypatch.setattr("madira.domain.pairing.copy.demo_lines", demo_boom)
    paired = _pair(client, review["menu_id"])
    assert paired.status_code == 200, paired.text
    assert "The model wrote this pairing rationale." in paired.text

    def explode(_prompt: str) -> str:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("madira.domain.pairing.copy.live_complete", explode)
    failed = _pair(client, other["menu_id"])
    assert failed.status_code == 502
    assert failed.json()["detail"] == "The pairing copy failed (RuntimeError)."
    assert "connection refused" not in failed.text


def test_demo_pairing_does_not_call_the_model_and_is_deterministic(client, monkeypatch):
    _sign_in(client, monkeypatch, _slug("pairing-demo"))
    _import_list(client)
    review = _menu(client, OCTOPUS)

    def explode(_prompt: str) -> str:
        raise AssertionError("live copy")

    monkeypatch.setattr("madira.domain.pairing.copy.live_complete", explode)
    first = _pair(client, review["menu_id"])
    second = _pair(client, review["menu_id"])
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    left = [(row["slot"], row["sku_id"], row["rationale"]) for row in _slots(first.json(), "Grilled octopus")]
    right = [(row["slot"], row["sku_id"], row["rationale"]) for row in _slots(second.json(), "Grilled octopus")]
    assert left == right
    assert any(row[1] for row in left)


def test_roles_and_venue_isolation(client, monkeypatch):
    venue = _sign_in(client, monkeypatch, _slug("pairing-roles"))
    _import_list(client)
    review = _menu(client, OCTOPUS)
    paired = _pair(client, review["menu_id"])
    assert paired.status_code == 200, paired.text
    dish = paired.json()["dishes"][0]
    pairing_id = dish["pairings"][0]["id"]

    other = _venue(_slug("pairing-other"))
    session = SessionLocal()
    try:
        secret = ensure_sku(session, other.id, category="wine", name="Other Venue Secret Bottle", producer="Hidden")
        beverage = BeverageList(venue_id=other.id, name="Other list", currency="USD")
        session.add(beverage)
        session.flush()
        session.add(
            ListItem(
                venue_id=other.id,
                list_id=beverage.id,
                sku_id=secret.id,
                pour_price=1000,
                bottle_price=4000,
                currency="USD",
            )
        )
        role_subs = {
            STAFF: f"{venue.slug}-staff",
            MANAGER: f"{venue.slug}-manager",
            AUDITOR: f"{venue.slug}-auditor",
            SOMMELIER: f"{venue.slug}-sommelier",
        }
        for role, sub in role_subs.items():
            _member(session, sub, f"{sub}@example.com", venue.id, role)
        session.commit()
        secret_id = str(secret.id)
    finally:
        session.close()

    _as(client, monkeypatch, f"owner-{venue.slug}")
    owned = client.get(f"/menus/{review['menu_id']}/pairings")
    assert owned.status_code == 200
    assert "Other Venue Secret Bottle" not in owned.text
    stolen = client.post(
        f"/menus/{review['menu_id']}/pairings/{pairing_id}/swap",
        json={"sku_id": secret_id},
    )
    assert stolen.status_code == 404

    _as(client, monkeypatch, f"{venue.slug}-staff")
    visible = client.get(f"/menus/{review['menu_id']}/pairings")
    assert visible.status_code == 200
    forbidden = client.post(f"/menus/{review['menu_id']}/pairings/{pairing_id}/pin")
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "This role cannot do that."

    _as(client, monkeypatch, f"{venue.slug}-manager")
    assert client.post(f"/menus/{review['menu_id']}/pairings/{pairing_id}/pin").status_code == 403

    _as(client, monkeypatch, f"{venue.slug}-auditor")
    hidden = client.get(f"/menus/{review['menu_id']}/pairings")
    assert hidden.status_code == 403
    assert hidden.json()["detail"] == "This role cannot do that."

    _as(client, monkeypatch, f"{venue.slug}-sommelier")
    allowed = client.post(f"/menus/{review['menu_id']}/pairings/{pairing_id}/pin")
    assert allowed.status_code == 200, allowed.text

    _as(client, monkeypatch, f"owner-{other.slug}")
    foreign = client.post(f"/menus/{review['menu_id']}/pairings/{pairing_id}/pin")
    assert foreign.status_code == 404
