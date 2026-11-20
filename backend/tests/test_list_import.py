"""CSV list import: preview, confirm, dedupe, bad rows, uploads, roles, venues."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from madira.auth import issue_session, utcnow
from madira.db import SessionLocal, init_db
from madira.domain.catalog.identity import norm
from madira.domain.catalog.service import ensure_sku, list_products
from madira.domain.lists.csv_import import DOCUMENTED_HEADERS
from madira.domain.lists.service import list_lists
from madira.main import app
from madira.models import BeverageList, Membership, Organization, Product, ProductVariant, Sku, User, Venue
from madira.money import DEFAULT_CURRENCY
from madira.seed import seed
from madira.storage import LocalDiskStorage, StorageError
from madira.tenancy import AUDITOR, MANAGER, OWNER, SOMMELIER, STAFF, ensure_demo_tenant

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "sample_list.csv"
AUTH_SECRET = "list-import-test-secret"
HEADERS = ",".join(DOCUMENTED_HEADERS)


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    monkeypatch.setenv("MADIRA_STORAGE_DIR", str(root))
    return root


@pytest.fixture
def client():
    init_db()
    seed()
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, body: bytes, *, confirm: bool = False, content_type: str = "text/csv", filename: str = "list.csv", name: str = ""):
    return client.post(
        "/lists/import",
        files={"file": (filename, body, content_type)},
        data={"confirm": "true" if confirm else "false", "name": name},
    )


def _cookie(monkeypatch, google_sub: str) -> str:
    monkeypatch.setenv("MADIRA_AUTH_SECRET", AUTH_SECRET)
    return issue_session(google_sub)


def _as(client: TestClient, monkeypatch, google_sub: str) -> None:
    client.cookies.set("madira_session", _cookie(monkeypatch, google_sub))


def _member(session, google_sub: str, email: str, venue_id, role: str) -> None:
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    now = utcnow()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=email, picture="", created_at=now, last_login_at=now)
        session.add(user)
        session.flush()
    membership = session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue_id)
    )
    if membership is None:
        session.add(Membership(user_id=user.id, venue_id=venue_id, role=role))
    else:
        membership.role = role


def _matches(organization_id, *, name: str, producer: str, category: str) -> list[Product]:
    key = (norm(category), norm(producer), norm(name))
    session = SessionLocal()
    try:
        rows = session.scalars(select(Product).where(Product.organization_id == organization_id)).all()
        return [row for row in rows if (norm(row.category), norm(row.producer), norm(row.name)) == key]
    finally:
        session.close()


def _csv(rows: list[str], header: str = "section,name,producer,vintage,region,country,category,style,grape,bottle size,bottle price,glass price,cost,barcode") -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


def test_storage_rejects_a_path_that_leaves_the_root(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    with pytest.raises(StorageError):
        storage.read("../secret")
    with pytest.raises(StorageError):
        storage.read("/etc/passwd")


def test_sample_preview_does_not_write_and_confirm_does(client: TestClient, storage_dir: Path):
    demo = ensure_demo_tenant()
    body = FIXTURE.read_bytes()
    assert body.splitlines()[0].decode() == HEADERS
    before = len(_matches(demo.organization_id, name="Muscadet Domaine de l'Ecu", producer="", category="wine"))
    assert before >= 1
    session = SessionLocal()
    try:
        lists_before = session.scalar(
            select(func.count()).select_from(BeverageList).where(BeverageList.source_filename == "sample_list.csv")
        )
    finally:
        session.close()

    preview = _post(client, body, filename="sample_list.csv")
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["mode"] == "preview"
    assert preview_body["currency"] == "USD"
    assert preview_body["errors"] == 0
    rows = {row["name"]: row for row in preview_body["rows"]}
    assert rows["Muscadet Domaine de l'Ecu"]["status"] == "match"
    assert rows["Chablis Premier Cru Vaillons"]["status"] in {"match", "new"}
    assert list(storage_dir.rglob("*.csv")) == []
    session = SessionLocal()
    try:
        assert (
            session.scalar(
                select(func.count()).select_from(BeverageList).where(BeverageList.source_filename == "sample_list.csv")
            )
            == lists_before
        )
    finally:
        session.close()

    chablis_before = len(
        _matches(
            demo.organization_id,
            name="Chablis Premier Cru Vaillons",
            producer="Jean-Paul & Benoît Droin",
            category="wine",
        )
    )
    confirmed = _post(client, body, confirm=True, filename="sample_list.csv")
    assert confirmed.status_code == 200, confirmed.text
    saved = confirmed.json()
    assert saved["mode"] == "confirmed"
    assert saved["list"]["source_filename"] == "sample_list.csv"
    assert saved["list"]["item_count"] == 5
    assert saved["list"]["source_key"].startswith(f"{demo.venue_id}/lists/")
    names = [item["name"] for item in saved["list"]["items"]]
    assert names[0] == "Muscadet Domaine de l'Ecu"
    chablis = next(item for item in saved["list"]["items"] if item["name"] == "Chablis Premier Cru Vaillons")
    assert chablis["producer"] == "Jean-Paul & Benoît Droin"
    assert chablis["section"] == "White"
    assert chablis["bottle_price"] == 9600
    assert chablis["pour_price"] == 2200
    assert chablis["cost"] == 3400
    assert chablis["currency"] == "USD"
    kolsch = next(item for item in saved["list"]["items"] if item["name"] == "Kölsch")
    assert kolsch["cost"] == 240
    assert kolsch["pour_price"] == 900
    stored = LocalDiskStorage(storage_dir).read(saved["list"]["source_key"])
    assert stored == body
    assert len(_matches(demo.organization_id, name="Muscadet Domaine de l'Ecu", producer="", category="wine")) == before
    chablis_after = len(
        _matches(
            demo.organization_id,
            name="Chablis Premier Cru Vaillons",
            producer="Jean-Paul & Benoît Droin",
            category="wine",
        )
    )
    assert chablis_after == max(chablis_before, 1)

    again = _post(client, body, confirm=True, filename="sample_list.csv")
    assert again.status_code == 200, again.text
    assert again.json()["new_products"] == 0
    assert len(
        _matches(
            demo.organization_id,
            name="Chablis Premier Cru Vaillons",
            producer="Jean-Paul & Benoît Droin",
            category="wine",
        )
    ) == chablis_after
    visible = list_lists(demo.venue_id)
    imported = next(row for row in visible["lists"] if row["id"] == uuid.UUID(saved["list"]["id"]))
    assert imported["items"][1]["name"] == "Chablis Premier Cru Vaillons"
    catalog = list_products(demo.venue_id)["products"]
    product = next(row for row in catalog if row["name"] == "Chablis Premier Cru Vaillons")
    assert product["body"] == ""
    assert product["aroma_families"] == []
    assert "embedding" not in product


def test_dedupes_on_producer_name_category_and_variant(client: TestClient):
    demo = ensure_demo_tenant()
    token = uuid.uuid4().hex[:8]
    name = f"Import Match {token}"
    session = SessionLocal()
    try:
        stock = ensure_sku(
            session,
            demo.venue_id,
            category="Wine",
            producer="  House   Maker ",
            name=f"  {name} ",
            region="Loire",
            vintage="2020",
            bottle_size="750ml",
            cost=100,
            currency=DEFAULT_CURRENCY,
        )
        product_id = stock.variant.product_id
        variant_id = stock.product_variant_id
        sku_id = stock.id
        session.commit()
    finally:
        session.close()

    body = _csv(
        [
            f"Red,{name.lower()},house maker,2020,Burgundy,France,wine,Other,Other,750 ML,40,12,11,",
            f"Red,{name},House Maker,2021,Loire,France,WINE,Other,Other,375ml,30,0,9,",
        ]
    )
    preview = _post(client, body)
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    assert rows[0]["status"] == "match"
    assert rows[0]["product_id"] == str(product_id)
    assert rows[0]["variant_id"] == str(variant_id)
    assert rows[1]["status"] == "new"
    assert rows[1]["action"] == "new_variant"
    assert preview.json()["new_products"] == 0

    confirmed = _post(client, body, confirm=True)
    assert confirmed.status_code == 200, confirmed.text
    assert len(_matches(demo.organization_id, name=name, producer="House Maker", category="wine")) == 1
    session = SessionLocal()
    try:
        product = session.get(Product, product_id)
        assert product.region == "Loire"
        assert product.body == ""
        variants = session.scalars(select(ProductVariant).where(ProductVariant.product_id == product_id)).all()
        assert {norm(row.bottle_size) for row in variants} == {"750ml", "375ml"}
        assert session.get(Sku, sku_id).cost == 100
    finally:
        session.close()


def test_prefers_the_product_that_already_has_the_variant(client: TestClient):
    demo = ensure_demo_tenant()
    token = uuid.uuid4().hex[:8]
    name = f"Twin Bottle {token}"
    barcode = f"TWIN-{token}".upper()
    session = SessionLocal()
    try:
        ensure_sku(
            session,
            demo.venue_id,
            category="wine",
            producer="Twin House",
            name=name,
            region="Loire",
            vintage="2020",
            bottle_size="",
        )
        sized = ensure_sku(
            session,
            demo.venue_id,
            category="wine",
            producer="Twin House",
            name=name,
            region="Burgundy",
            vintage="2020",
            bottle_size="750ml",
            barcode=barcode,
            cost=100,
        )
        sized_id = sized.variant.product_id
        session.commit()
    finally:
        session.close()

    body = _csv([f"Red,{name},Twin House,2020,Burgundy,France,wine,,,750 ML,40,12,11,{barcode}"])
    preview = _post(client, body)
    assert preview.status_code == 200, preview.text
    row = preview.json()["rows"][0]
    assert row["status"] == "match"
    assert row["product_id"] == str(sized_id)
    confirmed = _post(client, body, confirm=True)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["errors"] == 0
    assert len(_matches(demo.organization_id, name=name, producer="Twin House", category="wine")) == 2


def test_bad_rows_are_reported_and_do_not_crash(client: TestClient, storage_dir: Path):
    token = uuid.uuid4().hex[:8]
    good = f"Kept {token}"
    body = (
        "section,name,bottle price\n"
        "Red,,12\n"
        f"Red,Broken {token},abc\n"
        f"Red,{good},40\n"
        "\n"
    ).encode()
    preview = _post(client, body)
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["errors"] == 2
    assert payload["new"] == 1
    messages = {row["name"]: row["message"] for row in payload["rows"]}
    assert "Name is required." in messages[""]
    assert "Bottle price must be a number." in messages[f"Broken {token}"]
    confirmed = _post(client, body, confirm=True, name=f"Kept list {token}")
    assert confirmed.status_code == 200, confirmed.text
    assert [item["name"] for item in confirmed.json()["list"]["items"]] == [good]
    assert confirmed.json()["list"]["items"][0]["bottle_price"] == 4000
    stored = list(storage_dir.rglob("*.csv"))
    assert len(stored) == 1

    empty = _post(client, b"producer,region\nA,B\n")
    assert empty.status_code == 400
    assert empty.json()["detail"] == "The CSV needs a name column."
    rejected = _post(client, b"name\n\n", confirm=True)
    assert rejected.status_code == 400
    assert "Nothing to import" in rejected.json()["detail"]
    assert list(storage_dir.rglob("*.csv")) == stored
    garbled = _post(client, b"\xff\xfe not utf-8")
    assert garbled.status_code == 400
    assert garbled.json()["detail"] == "This file is not UTF-8 text."


def test_duplicate_rows_create_one_product(client: TestClient):
    token = uuid.uuid4().hex[:8]
    name = f"Twin {token}"
    body = _csv(
        [
            f"Red,{name},House,2020,Loire,France,wine,Red,Cabernet,750ml,40,10,12,TWIN-{token}",
            f"Red,{name},House,2020,Loire,France,wine,Red,Cabernet,750ml,41,10,12,TWIN-{token}",
            f"Red,{name},House,2021,Loire,France,wine,Red,Cabernet,750ml,42,10,12,",
        ]
    )
    preview = _post(client, body)
    assert preview.status_code == 200, preview.text
    assert [row["action"] for row in preview.json()["rows"]] == ["new_product", "duplicate", "new_variant"]
    confirmed = _post(client, body, confirm=True)
    assert confirmed.status_code == 200, confirmed.text
    demo = ensure_demo_tenant()
    assert len(_matches(demo.organization_id, name=name, producer="House", category="wine")) == 1
    assert confirmed.json()["list"]["item_count"] == 2


def test_upload_limits(client: TestClient, monkeypatch, storage_dir: Path):
    monkeypatch.setenv("MADIRA_UPLOAD_MAX_BYTES", "32")
    oversized = _post(client, b"name,producer\n" + b"A,B\n" * 10)
    assert oversized.status_code == 413
    assert oversized.json()["detail"] == "This file is larger than the upload limit."
    wrong_type = _post(client, b"name\nHello\n", content_type="image/png", filename="list.csv")
    assert wrong_type.status_code == 415
    assert wrong_type.json()["detail"] == "This file type is not accepted."
    unnamed = _post(client, b"name\nHello\n", content_type="application/octet-stream", filename="notes.bin")
    assert unnamed.status_code == 415
    empty = _post(client, b"", content_type="text/csv")
    assert empty.status_code == 400
    assert empty.json()["detail"] == "This file is empty."
    binary = _post(client, b"name\nhel\x00lo\n", content_type="text/csv")
    assert binary.status_code == 415
    monkeypatch.setenv("MADIRA_UPLOAD_MAX_BYTES", "2097152")
    typed = _post(client, "name,producer\nAlias Bottle,Alias House\n".encode(), content_type="text/csv; charset=utf-8")
    assert typed.status_code == 200, typed.text
    plain = _post(
        client,
        "Section,Wine,Winery,Year,Appellation,Country,Type,Style,Varietal,Size,Bottle Price,Pour,Unit Cost,UPC\nRed,Alias Bottle,Alias House,2022,Loire,France,wine,Red,Cabernet,750ml,$40,12,11,ALIAS-1\n".encode(),
        content_type="application/octet-stream",
        filename="alias.csv",
        confirm=True,
    )
    assert plain.status_code == 200, plain.text
    item = plain.json()["list"]["items"][0]
    assert item["name"] == "Alias Bottle"
    assert item["producer"] == "Alias House"
    assert item["vintage"] == "2022"
    assert item["bottle_price"] == 4000
    assert item["pour_price"] == 1200
    assert item["cost"] == 1100
    assert list(storage_dir.rglob("*.csv"))


def test_aliases_use_the_venue_currency(client: TestClient, monkeypatch):
    demo = ensure_demo_tenant()
    token = uuid.uuid4().hex[:8]
    session = SessionLocal()
    try:
        venue = Venue(organization_id=demo.organization_id, name=f"Euro {token}", slug=f"euro-{token}", currency="EUR")
        session.add(venue)
        session.flush()
        _member(session, f"euro-{token}", f"euro-{token}@example.com", venue.id, OWNER)
        session.commit()
        venue_id = venue.id
    finally:
        session.close()

    _as(client, monkeypatch, f"euro-{token}")
    body = _csv(
        [f"White,Euro Bottle {token},Euro House,2018,Mosel,Germany,wine,Riesling,Riesling,750ml,18.50,6,9.25,"]
    )
    confirmed = _post(client, body, confirm=True)
    assert confirmed.status_code == 200, confirmed.text
    saved = confirmed.json()
    assert saved["currency"] == "EUR"
    assert saved["list"]["currency"] == "EUR"
    assert saved["list"]["items"][0]["currency"] == "EUR"
    assert saved["list"]["items"][0]["bottle_price"] == 1850
    assert saved["list"]["items"][0]["cost"] == 925
    session = SessionLocal()
    try:
        sku = session.scalar(select(Sku).where(Sku.venue_id == venue_id))
        assert sku.currency == "EUR"
        assert sku.cost == 925
    finally:
        session.close()


def test_import_roles(client: TestClient, monkeypatch):
    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        roles = {
            "import-owner": (OWNER, "import-owner@example.com"),
            "import-sommelier": (SOMMELIER, "import-sommelier@example.com"),
            "import-manager": (MANAGER, "import-manager@example.com"),
            "import-staff": (STAFF, "import-staff@example.com"),
            "import-auditor": (AUDITOR, "import-auditor@example.com"),
        }
        for sub, (role, email) in roles.items():
            _member(session, sub, email, demo.venue_id, role)
        session.commit()
    finally:
        session.close()

    body = b"name\nRole Bottle\n"
    for sub in ("import-manager", "import-staff", "import-auditor"):
        _as(client, monkeypatch, sub)
        response = _post(client, body, confirm=True)
        assert response.status_code == 403
        assert response.json()["detail"] == "This role cannot do that."
    for sub in ("import-owner", "import-sommelier"):
        _as(client, monkeypatch, sub)
        response = _post(client, body)
        assert response.status_code == 200, response.text


def test_lists_stay_inside_the_venue_and_products_dedupe_inside_the_org(client: TestClient, monkeypatch):
    demo = ensure_demo_tenant()
    token = uuid.uuid4().hex[:8]
    name = f"Cellar Only {token}"
    session = SessionLocal()
    try:
        other_org = Organization(name=f"Other {token}", slug=f"other-{token}")
        session.add(other_org)
        session.flush()
        sibling = Venue(organization_id=demo.organization_id, name=f"Sibling {token}", slug=f"sibling-{token}")
        outsider = Venue(organization_id=other_org.id, name=f"Outsider {token}", slug=f"outsider-{token}")
        session.add_all([sibling, outsider])
        session.flush()
        _member(session, f"sibling-{token}", f"sibling-{token}@example.com", sibling.id, OWNER)
        _member(session, f"outsider-{token}", f"outsider-{token}@example.com", outsider.id, OWNER)
        session.commit()
        sibling_id = sibling.id
        outsider_id = outsider.id
        other_org_id = other_org.id
    finally:
        session.close()

    body = _csv([f"Red,{name},Private,2016,Rhone,France,wine,Syrah,Syrah,750ml,80,20,30,ONLY-{token}"])
    confirmed = _post(client, body, confirm=True)
    assert confirmed.status_code == 200, confirmed.text
    list_id = confirmed.json()["list"]["id"]
    assert confirmed.json()["list"]["source_key"].startswith(f"{demo.venue_id}/")

    _as(client, monkeypatch, f"sibling-{token}")
    sibling_lists = client.get("/lists")
    assert sibling_lists.status_code == 200
    assert list_id not in {row["id"] for row in sibling_lists.json()["lists"]}
    sibling_names = {row["name"] for row in client.get("/products").json()["products"]}
    assert name not in sibling_names
    sibling_import = _post(client, body, confirm=True)
    assert sibling_import.status_code == 200, sibling_import.text
    assert sibling_import.json()["matched"] == 1
    assert sibling_import.json()["new_products"] == 0
    assert sibling_import.json()["list"]["source_key"].startswith(f"{sibling_id}/")
    assert len(_matches(demo.organization_id, name=name, producer="Private", category="wine")) == 1

    _as(client, monkeypatch, f"outsider-{token}")
    outsider_import = _post(client, body, confirm=True)
    assert outsider_import.status_code == 200, outsider_import.text
    assert outsider_import.json()["new_products"] == 1
    assert outsider_import.json()["list"]["source_key"].startswith(f"{outsider_id}/")
    assert len(_matches(other_org_id, name=name, producer="Private", category="wine")) == 1
    session = SessionLocal()
    try:
        code = f"ONLY-{token}".upper()
        assert session.scalar(select(func.count()).select_from(Sku).where(Sku.venue_id == sibling_id, Sku.barcode == code)) == 1
        assert session.scalar(select(func.count()).select_from(Sku).where(Sku.venue_id == demo.venue_id, Sku.barcode == code)) == 1
    finally:
        session.close()
