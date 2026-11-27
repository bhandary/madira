"""S3-compatible storage: published SigV4 vectors, a fake bucket, and the routes.

The access key and secret below are the credentials in AWS's public signing
examples. They are not a real account. No test opens a socket.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from madira.auth import issue_session, utcnow
from madira.db import SessionLocal
from madira.main import app
from madira.models import Membership, User, Venue
from madira.s3sig import canonical_request, presign_url, signature_hex, sign_headers, string_to_sign
from madira.storage import LocalDiskStorage, S3Storage, StorageError, get_storage, key_in_venue
from madira.tenancy import OWNER, ensure_demo_tenant

# AWS's published example credentials. Not a real account.
ACCESS = "AKIAIOSFODNN7EXAMPLE"
SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
WHEN = datetime(2013, 5, 24, tzinfo=timezone.utc)

GET_CANONICAL = (
    "GET\n"
    "/test.txt\n"
    "\n"
    "host:examplebucket.s3.amazonaws.com\n"
    "range:bytes=0-9\n"
    "x-amz-content-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n"
    "x-amz-date:20130524T000000Z\n"
    "\n"
    "host;range;x-amz-content-sha256;x-amz-date\n"
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
GET_TO_SIGN = (
    "AWS4-HMAC-SHA256\n"
    "20130524T000000Z\n"
    "20130524/us-east-1/s3/aws4_request\n"
    "7344ae5b7ee6c3e7e6b0fe0640412a37625d1fbfff95c48bbb2dc43964946972"
)
GET_SIGNATURE = "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
GET_AUTHORIZATION = (
    "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,"
    "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,"
    f"Signature={GET_SIGNATURE}"
)
PRESIGNED = (
    "https://examplebucket.s3.amazonaws.com/test.txt"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=AKIAIOSFODNN7EXAMPLE%2F20130524%2Fus-east-1%2Fs3%2Faws4_request"
    "&X-Amz-Date=20130524T000000Z"
    "&X-Amz-Expires=86400"
    "&X-Amz-SignedHeaders=host"
    "&X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
)
PUT_HASH = "44ce7dd67c959e0d3524ffac1771dfbba87d2b6b4b4e99e42034a8b803f8b072"
PUT_CANONICAL = (
    "PUT\n"
    "/test%24file.text\n"
    "\n"
    "date:Fri, 24 May 2013 00:00:00 GMT\n"
    "host:examplebucket.s3.amazonaws.com\n"
    "x-amz-content-sha256:44ce7dd67c959e0d3524ffac1771dfbba87d2b6b4b4e99e42034a8b803f8b072\n"
    "x-amz-date:20130524T000000Z\n"
    "x-amz-storage-class:REDUCED_REDUNDANCY\n"
    "\n"
    "date;host;x-amz-content-sha256;x-amz-date;x-amz-storage-class\n"
    "44ce7dd67c959e0d3524ffac1771dfbba87d2b6b4b4e99e42034a8b803f8b072"
)
PUT_TO_SIGN = (
    "AWS4-HMAC-SHA256\n"
    "20130524T000000Z\n"
    "20130524/us-east-1/s3/aws4_request\n"
    "9e0e90d9c76de8fa5b200d8c849cd5b8dc7a3be3951ddb7f6a76b4158342019d"
)
PUT_SIGNATURE = "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"

FAKE_SECRET = "secret-key-not-for-logs"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_published_get_and_put_vectors():
    headers = [
        ("host", "examplebucket.s3.amazonaws.com"),
        ("range", "bytes=0-9"),
        ("x-amz-content-sha256", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        ("x-amz-date", "20130524T000000Z"),
    ]
    canonical = canonical_request("GET", "/test.txt", [], headers, headers[2][1])
    assert canonical == GET_CANONICAL
    to_sign = string_to_sign(canonical, amz="20130524T000000Z", region="us-east-1")
    assert to_sign == GET_TO_SIGN
    assert signature_hex(to_sign, secret=SECRET, date_stamp="20130524", region="us-east-1") == GET_SIGNATURE
    signed = sign_headers(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        uri="/test.txt",
        region="us-east-1",
        access_key=ACCESS,
        secret=SECRET,
        payload=b"",
        content_type=None,
        now=WHEN,
        extra_headers=[("range", "bytes=0-9")],
    )
    assert signed["authorization"] == GET_AUTHORIZATION
    assert SECRET not in signed["authorization"]

    put = canonical_request(
        "PUT",
        "/test%24file.text",
        [],
        [
            ("date", "Fri, 24 May 2013 00:00:00 GMT"),
            ("host", "examplebucket.s3.amazonaws.com"),
            ("x-amz-content-sha256", PUT_HASH),
            ("x-amz-date", "20130524T000000Z"),
            ("x-amz-storage-class", "REDUCED_REDUNDANCY"),
        ],
        PUT_HASH,
    )
    assert put == PUT_CANONICAL
    put_sign = string_to_sign(put, amz="20130524T000000Z", region="us-east-1")
    assert put_sign == PUT_TO_SIGN
    assert signature_hex(put_sign, secret=SECRET, date_stamp="20130524", region="us-east-1") == PUT_SIGNATURE


def test_published_presigned_url():
    url = presign_url(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        uri="/test.txt",
        region="us-east-1",
        access_key=ACCESS,
        secret=SECRET,
        now=WHEN,
        expires=86400,
    )
    assert url == PRESIGNED
    assert SECRET not in url


def _storage(handler, **kwargs) -> S3Storage:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return S3Storage(
        bucket="venue-files",
        region="us-east-1",
        access_key="AKIATESTKEY",
        secret_key=FAKE_SECRET,
        endpoint="http://127.0.0.1:9000",
        client=client,
        now=lambda: WHEN,
        **kwargs,
    )


def test_s3_backend_put_get_head_delete_and_errors():
    bodies = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert FAKE_SECRET not in request.headers.get("authorization", "")
        assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256 ")
        key = request.url.path.split("/", 2)[-1]
        if request.method == "PUT":
            if request.url.path.endswith("/boom"):
                return httpx.Response(500, text=FAKE_SECRET)
            bodies[key] = request.content
            return httpx.Response(200)
        if request.method == "GET":
            if key not in bodies:
                return httpx.Response(404, text="NoSuchKey")
            return httpx.Response(200, content=bodies[key])
        if request.method == "HEAD":
            return httpx.Response(200 if key in bodies else 404)
        if request.method == "DELETE":
            if key not in bodies:
                return httpx.Response(404)
            del bodies[key]
            return httpx.Response(204)
        return httpx.Response(500, text=FAKE_SECRET)

    org = uuid.uuid4()
    venue = uuid.uuid4()
    storage = _storage(handler)
    stored = storage.put(
        venue,
        kind="vault",
        body=b"cellar note",
        content_type="text/plain",
        filename="note.txt",
        allowed_types=frozenset({"text/plain"}),
        organization_id=org,
    )
    assert stored.key.startswith(f"{org}/{venue}/vault/")
    assert storage.head(stored.key) is True
    assert storage.read(stored.key) == b"cellar note"
    assert storage.head("missing/object") is False
    with pytest.raises(StorageError) as missing:
        storage.read(f"{org}/{venue}/vault/missing")
    assert missing.value.status == 404
    assert FAKE_SECRET not in missing.value.message
    storage.delete(stored.key)
    assert storage.head(stored.key) is False
    storage.delete(stored.key)
    direct = storage._send("PUT", f"{org}/{venue}/vault/boom", b"x", "text/plain")
    assert direct.status_code == 500
    with pytest.raises(StorageError) as mapped:
        storage._map(direct, missing="Unknown file.", failed="This file could not be stored.")
    assert mapped.value.status == 502
    assert FAKE_SECRET not in mapped.value.message
    assert "NoSuchKey" not in mapped.value.message


def test_keys_are_namespaced_by_org_and_venue_and_disk_is_not():
    org = uuid.uuid4()
    venue = uuid.uuid4()
    other = uuid.uuid4()
    assert key_in_venue(f"{venue}/vault/abc", venue, "vault")
    assert key_in_venue(f"{org}/{venue}/vault/abc", venue, "vault")
    assert not key_in_venue(f"{other}/vault/abc", venue, "vault")
    assert not key_in_venue(f"{org}/{other}/vault/abc", venue, "vault")
    assert not key_in_venue(f"../{venue}/vault/abc", venue, "vault")
    disk = LocalDiskStorage()
    assert "organization_id" in disk.put.__code__.co_varnames


def test_disk_mode_is_unchanged(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.delenv("MADIRA_STORAGE", raising=False)
    monkeypatch.setenv("MADIRA_STORAGE_DIR", str(tmp_path))
    storage = get_storage()
    assert isinstance(storage, LocalDiskStorage)
    demo = ensure_demo_tenant()
    stored = storage.put(
        demo.venue_id,
        kind="vault",
        body=b"on disk",
        content_type="text/plain",
        filename="note.txt",
        allowed_types=frozenset({"text/plain"}),
        organization_id=demo.organization_id,
    )
    assert stored.key.startswith(f"{demo.venue_id}/vault/")
    assert str(demo.organization_id) not in stored.key
    assert storage.read(stored.key) == b"on disk"
    uploaded = client.post(
        "/compliance/documents",
        files={"file": ("cellar.txt", b"cellar note", "text/plain")},
        data={"doc_type": "other"},
    )
    assert uploaded.status_code == 200, uploaded.text
    document_id = uploaded.json()["document"]["id"]
    downloaded = client.get(f"/compliance/documents/{document_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"cellar note"
    assert downloaded.headers["content-type"].startswith("text/plain")
    assert "location" not in downloaded.headers


def test_signed_url_is_issued_only_after_role_and_venue_checks(client: TestClient, monkeypatch, caplog):
    monkeypatch.setenv("MADIRA_STORAGE", "s3")
    monkeypatch.setenv("MADIRA_S3_BUCKET", "venue-files")
    monkeypatch.setenv("MADIRA_S3_REGION", "us-east-1")
    monkeypatch.setenv("MADIRA_S3_ENDPOINT", "http://127.0.0.1:9000")
    monkeypatch.setenv("MADIRA_S3_ACCESS_KEY", "AKIATESTKEY")
    monkeypatch.setenv("MADIRA_S3_SECRET_KEY", FAKE_SECRET)
    monkeypatch.setenv("MADIRA_S3_URL_EXPIRES", "60")
    saved: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert FAKE_SECRET not in str(request.headers)
        if request.method == "PUT":
            saved[request.url.path] = request.content
            return httpx.Response(200)
        return httpx.Response(500, text=FAKE_SECRET)

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )
    signed: list[str] = []
    original = S3Storage.presign_get

    def spy(self, key, **kwargs):
        signed.append(key)
        return original(self, key, **kwargs)

    monkeypatch.setattr(S3Storage, "presign_get", spy)
    uploaded = client.post(
        "/compliance/documents",
        files={"file": ("cellar.txt", b"cellar note", "text/plain")},
        data={"doc_type": "other"},
    )
    assert uploaded.status_code == 200, uploaded.text
    document_id = uploaded.json()["document"]["id"]
    demo = ensure_demo_tenant()
    assert saved
    assert any(f"/{demo.organization_id}/{demo.venue_id}/vault/" in path for path in saved)

    client.cookies.set("madira_demo_persona", "ana")
    denied = client.get(f"/compliance/documents/{document_id}/download", follow_redirects=False)
    assert denied.status_code == 403
    assert signed == []
    client.cookies.clear()

    session = SessionLocal()
    try:
        venue = session.scalar(select(Venue).where(Venue.slug == "s3-other"))
        if venue is None:
            venue = Venue(organization_id=demo.organization_id, name="S3 Other", slug="s3-other")
            session.add(venue)
            session.flush()
        user = session.scalar(select(User).where(User.google_sub == "s3-other-owner"))
        now = utcnow()
        if user is None:
            user = User(google_sub="s3-other-owner", email="s3-other@example.com", name="Other", picture="", created_at=now, last_login_at=now)
            session.add(user)
            session.flush()
        membership = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.venue_id == venue.id))
        if membership is None:
            session.add(Membership(user_id=user.id, venue_id=venue.id, role=OWNER))
        session.commit()
    finally:
        session.close()
    monkeypatch.setenv("MADIRA_AUTH_SECRET", "s3-storage-test-secret")
    client.cookies.set("madira_session", issue_session("s3-other-owner"))
    foreign = client.get(f"/compliance/documents/{document_id}/download", follow_redirects=False)
    assert foreign.status_code == 404
    assert signed == []
    client.cookies.clear()

    caplog.set_level(logging.INFO, logger="madira.storage")
    allowed = client.get(f"/compliance/documents/{document_id}/download", follow_redirects=False)
    assert allowed.status_code == 302
    location = allowed.headers["location"]
    assert location.startswith("http://127.0.0.1:9000/venue-files/")
    assert "X-Amz-Signature=" in location
    assert "X-Amz-Expires=60" in location
    assert FAKE_SECRET not in location
    assert signed and signed[0] in location
    text = caplog.text
    assert signed[0] in text
    assert FAKE_SECRET not in text
    assert "AKIATESTKEY" not in text
    assert "X-Amz-Signature" not in text


def test_s3_without_a_bucket_is_not_configured(monkeypatch):
    monkeypatch.setenv("MADIRA_STORAGE", "s3")
    monkeypatch.delenv("MADIRA_S3_BUCKET", raising=False)
    with pytest.raises(StorageError) as exc:
        get_storage()
    assert exc.value.status == 500
    assert "secret" not in exc.value.message.lower()
