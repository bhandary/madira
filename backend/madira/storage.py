"""File storage for uploads.

Menus, lists, and labels share this. A caller passes the bytes, the content
type, and the types it accepts. This module checks the size and the content
type, then stores the bytes. It does not interpret them: an upload is
untrusted data.

The local disk is the default. It keeps each venue's files under
``{venue_id}/``. ``MADIRA_STORAGE_DIR`` is the root (default
``backend/data/storage``). ``MADIRA_UPLOAD_MAX_BYTES`` caps one file at
2 MiB unless set, and never above 20 MiB. Text uploads reject null bytes.
A caller that stores a photo or PDF passes ``binary=True`` so those bytes
are kept as-is.

``MADIRA_STORAGE=s3`` stores the same bytes in an S3-compatible bucket.
Object keys are ``{organization_id}/{venue_id}/{kind}/...``. Disk keys stay
``{venue_id}/{kind}/...``. Routes that serve a stored file keep returning
the bytes in disk mode. In s3 mode they redirect to a short-lived signed
GET after the role and venue checks, so the object is not pulled back
through the app.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx
from fastapi.responses import RedirectResponse, Response

from madira.config import DATA_DIR
from madira.s3sig import presign_url, sign_headers

logger = logging.getLogger("madira.storage")

_DEFAULT_MAX_BYTES = 2 * 1024 * 1024
_MAX_BYTES_CEILING = 20 * 1024 * 1024
_KIND = re.compile(r"^[a-z0-9_-]{1,32}$")


class StorageError(Exception):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    content_type: str


class Storage(Protocol):
    def check(
        self,
        *,
        body: bytes,
        content_type: str | None,
        filename: str,
        allowed_types: frozenset[str],
        fallback_extension: str = "",
        binary: bool = False,
    ) -> str: ...

    def put(
        self,
        venue_id: uuid.UUID,
        *,
        kind: str,
        body: bytes,
        content_type: str | None,
        filename: str,
        allowed_types: frozenset[str],
        fallback_extension: str = "",
        binary: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> StoredFile: ...

    def read(self, key: str) -> bytes: ...

    def head(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


def upload_max_bytes() -> int:
    raw = os.environ.get("MADIRA_UPLOAD_MAX_BYTES", "").strip()
    if not raw:
        return _DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_BYTES
    if value < 1:
        return _DEFAULT_MAX_BYTES
    return min(value, _MAX_BYTES_CEILING)


def storage_root() -> Path:
    raw = os.environ.get("MADIRA_STORAGE_DIR", "").strip()
    return Path(raw) if raw else DATA_DIR / "storage"


def normalize_content_type(value: str | None) -> str:
    if not value:
        return ""
    return value.split(";", 1)[0].strip().lower()


def key_in_venue(key: str, venue_id: uuid.UUID, kind: str) -> bool:
    """True when ``key`` is that venue's object and not a path escape.

    Disk keys are ``{venue}/{kind}/name``. S3 keys add the organization in
    front: ``{organization}/{venue}/{kind}/name``.
    """

    if not key or key.startswith(("/", "\\")) or "\\" in key:
        return False
    parts = key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    venue = str(venue_id)
    if len(parts) >= 3 and parts[0] == venue and parts[1] == kind:
        return True
    if len(parts) >= 4 and parts[1] == venue and parts[2] == kind:
        try:
            uuid.UUID(parts[0])
        except ValueError:
            return False
        return True
    return False


def _object_name(fallback_extension: str) -> str:
    suffix = fallback_extension.lower() if fallback_extension.startswith(".") else ""
    return f"{uuid.uuid4().hex}{suffix}"


def _encode_key(key: str) -> str:
    return "/".join(quote(part, safe="-_.~") for part in key.split("/"))


class LocalDiskStorage:
    """Writes under ``root / venue_id / kind /``. The stored name is generated."""

    def __init__(self, root: Path | None = None, max_bytes: int | None = None) -> None:
        self.root = root or storage_root()
        self.max_bytes = _DEFAULT_MAX_BYTES if max_bytes is None else max_bytes

    def check(
        self,
        *,
        body: bytes,
        content_type: str | None,
        filename: str,
        allowed_types: frozenset[str],
        fallback_extension: str = "",
        binary: bool = False,
    ) -> str:
        if len(body) > self.max_bytes:
            raise StorageError("This file is larger than the upload limit.", 413)
        if not body:
            raise StorageError("This file is empty.", 400)
        if not binary and b"\x00" in body:
            raise StorageError("This file is not text.", 415)
        media = normalize_content_type(content_type)
        if media in allowed_types:
            return media
        extension = fallback_extension.lower()
        unnamed = media in {"", "application/octet-stream"}
        if unnamed and extension.startswith(".") and Path(filename or "").name.lower().endswith(extension):
            return "text/csv" if "text/csv" in allowed_types else next(iter(allowed_types))
        raise StorageError("This file type is not accepted.", 415)

    def put(
        self,
        venue_id: uuid.UUID,
        *,
        kind: str,
        body: bytes,
        content_type: str | None,
        filename: str,
        allowed_types: frozenset[str],
        fallback_extension: str = "",
        binary: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> StoredFile:
        del organization_id
        media = self.check(
            body=body,
            content_type=content_type,
            filename=filename,
            allowed_types=allowed_types,
            fallback_extension=fallback_extension,
            binary=binary,
        )
        if not isinstance(venue_id, uuid.UUID) or not _KIND.match(kind):
            raise StorageError("This file could not be stored.", 400)
        directory = self.root / str(venue_id) / kind
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}{fallback_extension.lower() if fallback_extension.startswith('.') else ''}"
        path = directory / name
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_bytes(body)
        temporary.replace(path)
        key = f"{venue_id}/{kind}/{name}"
        return StoredFile(key=key, size=len(body), content_type=media)

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def head(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()

    def _resolve(self, key: str) -> Path:
        if not key or ".." in Path(key).parts or key.startswith(("/", "\\")):
            raise StorageError("Unknown file.", 404)
        root = self.root.resolve()
        path = (self.root / key).resolve()
        if not path.is_relative_to(root):
            raise StorageError("Unknown file.", 404)
        return path


def _url_expires() -> int:
    raw = os.environ.get("MADIRA_S3_URL_EXPIRES", "").strip()
    if not raw:
        return 60
    try:
        value = int(raw)
    except ValueError:
        return 60
    if value < 1:
        return 60
    return min(value, 900)


def _required_s3(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise StorageError("Object storage is not configured.", 500)
    return value


class S3Storage:
    """S3-compatible objects. Signing uses :mod:`madira.s3sig`. No SDK."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        endpoint: str = "",
        expires: int = 60,
        max_bytes: int | None = None,
        client: httpx.Client | None = None,
        now=None,
    ) -> None:
        if not bucket or "/" in bucket or ".." in bucket:
            raise StorageError("Object storage is not configured.", 500)
        if not region or "/" in region:
            raise StorageError("Object storage is not configured.", 500)
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint.rstrip("/")
        self.expires = expires
        self.max_bytes = _DEFAULT_MAX_BYTES if max_bytes is None else max_bytes
        self.client = client
        self._now = now

    @classmethod
    def from_env(cls, client: httpx.Client | None = None) -> S3Storage:
        endpoint = os.environ.get("MADIRA_S3_ENDPOINT", "").strip()
        return cls(
            bucket=_required_s3("MADIRA_S3_BUCKET"),
            region=_required_s3("MADIRA_S3_REGION"),
            access_key=_required_s3("MADIRA_S3_ACCESS_KEY"),
            secret_key=_required_s3("MADIRA_S3_SECRET_KEY"),
            endpoint=endpoint,
            expires=_url_expires(),
            max_bytes=upload_max_bytes(),
            client=client,
        )

    def check(
        self,
        *,
        body: bytes,
        content_type: str | None,
        filename: str,
        allowed_types: frozenset[str],
        fallback_extension: str = "",
        binary: bool = False,
    ) -> str:
        return LocalDiskStorage(max_bytes=self.max_bytes).check(
            body=body,
            content_type=content_type,
            filename=filename,
            allowed_types=allowed_types,
            fallback_extension=fallback_extension,
            binary=binary,
        )

    def _clock(self) -> datetime:
        if self._now is not None:
            return self._now() if callable(self._now) else self._now
        return datetime.now(timezone.utc)

    def _target(self, key: str) -> tuple[str, str, str]:
        """Return scheme, host, and the canonical URI for ``key``."""

        encoded = _encode_key(key)
        if self.endpoint:
            parsed = urlparse(self.endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise StorageError("Object storage is not configured.", 500)
            host = parsed.hostname
            if parsed.port and not (
                (parsed.scheme == "https" and parsed.port == 443) or (parsed.scheme == "http" and parsed.port == 80)
            ):
                host = f"{host}:{parsed.port}"
            return parsed.scheme, host, f"/{self.bucket}/{encoded}"
        host = f"{self.bucket}.s3.amazonaws.com" if self.region == "us-east-1" else f"{self.bucket}.s3.{self.region}.amazonaws.com"
        return "https", host, f"/{encoded}"

    def _guard(self, key: str) -> None:
        if not key or ".." in key.split("/") or key.startswith(("/", "\\")) or "\\" in key:
            raise StorageError("Unknown file.", 404)

    def _send(self, method: str, key: str, body: bytes = b"", content_type: str | None = None) -> httpx.Response:
        self._guard(key)
        scheme, host, uri = self._target(key)
        headers = sign_headers(
            method=method,
            host=host,
            uri=uri,
            region=self.region,
            access_key=self.access_key,
            secret=self.secret_key,
            payload=body,
            content_type=content_type,
            now=self._clock(),
        )
        url = f"{scheme}://{host}{uri}"
        client = self.client
        close = False
        if client is None:
            client = httpx.Client(timeout=30.0)
            close = True
        try:
            return client.request(method, url, headers=headers, content=body if method != "HEAD" else None, follow_redirects=False)
        finally:
            if close:
                client.close()

    def _map(self, response: httpx.Response, *, missing: str, failed: str) -> None:
        if response.status_code in {200, 201, 204}:
            return
        if response.status_code == 404:
            raise StorageError(missing, 404)
        raise StorageError(failed, 502)

    def put(
        self,
        venue_id: uuid.UUID,
        *,
        kind: str,
        body: bytes,
        content_type: str | None,
        filename: str,
        allowed_types: frozenset[str],
        fallback_extension: str = "",
        binary: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> StoredFile:
        media = self.check(
            body=body,
            content_type=content_type,
            filename=filename,
            allowed_types=allowed_types,
            fallback_extension=fallback_extension,
            binary=binary,
        )
        org = organization_id
        if org is None:
            from madira.tenancy import current_request

            ctx = current_request()
            org = None if ctx is None else ctx.organization_id
        if not isinstance(venue_id, uuid.UUID) or not isinstance(org, uuid.UUID) or not _KIND.match(kind):
            raise StorageError("This file could not be stored.", 400)
        name = _object_name(fallback_extension)
        key = f"{org}/{venue_id}/{kind}/{name}"
        response = self._send("PUT", key, body, media)
        self._map(response, missing="This file could not be stored.", failed="This file could not be stored.")
        logger.info("storage put key=%s", key)
        return StoredFile(key=key, size=len(body), content_type=media)

    def read(self, key: str) -> bytes:
        response = self._send("GET", key)
        self._map(response, missing="Unknown file.", failed="This file could not be read.")
        logger.info("storage get key=%s", key)
        return response.content

    def head(self, key: str) -> bool:
        response = self._send("HEAD", key)
        if response.status_code == 404:
            return False
        self._map(response, missing="Unknown file.", failed="This file could not be read.")
        logger.info("storage head key=%s", key)
        return True

    def delete(self, key: str) -> None:
        response = self._send("DELETE", key)
        if response.status_code == 404:
            return
        self._map(response, missing="Unknown file.", failed="This file could not be deleted.")
        logger.info("storage delete key=%s", key)

    def presign_get(self, key: str, *, filename: str, media: str, disposition: str) -> str:
        self._guard(key)
        scheme, host, uri = self._target(key)
        quoted = filename.replace("\\", "").replace('"', "").replace("\r", "").replace("\n", "")
        url = presign_url(
            method="GET",
            host=host,
            uri=uri,
            region=self.region,
            access_key=self.access_key,
            secret=self.secret_key,
            now=self._clock(),
            expires=self.expires,
            scheme=scheme,
            extra_query=[
                ("response-content-disposition", f'{disposition}; filename="{quoted}"'),
                ("response-content-type", media or "application/octet-stream"),
            ],
        )
        logger.info("storage presign key=%s", key)
        return url


def storage_mode() -> str:
    return os.environ.get("MADIRA_STORAGE", "").strip().lower()


def get_storage() -> Storage:
    mode = storage_mode()
    if mode in {"", "disk", "local"}:
        return LocalDiskStorage(storage_root(), upload_max_bytes())
    if mode == "s3":
        return S3Storage.from_env()
    raise StorageError("Object storage is not configured.", 500)


def stored_file_response(*, key: str, filename: str, media: str, disposition: str = "attachment") -> Response:
    """Serve a stored file.

    Disk mode returns the bytes. S3 mode redirects to a signed GET. The
    redirect is chosen so the browser fetches the object from the bucket
    after this app has already checked the role and the venue. The signed
    URL is not logged.
    """

    storage = get_storage()
    quoted = filename.replace("\\", "").replace('"', "").replace("\r", "").replace("\n", "")
    if isinstance(storage, S3Storage):
        url = storage.presign_get(key, filename=quoted or "download", media=media, disposition=disposition)
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    payload = storage.read(key)
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'{disposition}; filename="{quoted}"'},
    )
