"""File storage for uploads.

Menus, lists, and labels share this. A caller passes the bytes, the content
type, and the types it accepts. This module checks the size and the content
type, then stores the bytes. It does not interpret them: an upload is
untrusted data.

The local disk keeps each venue's files under ``{venue_id}/``.
``MADIRA_STORAGE_DIR`` is the root (default ``backend/data/storage``).
``MADIRA_UPLOAD_MAX_BYTES`` caps one file at 2 MiB unless set, and never
above 20 MiB. Text uploads reject null bytes. A caller that stores a photo
or PDF passes ``binary=True`` so those bytes are kept as-is.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from madira.config import DATA_DIR

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
    ) -> StoredFile: ...

    def read(self, key: str) -> bytes: ...

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
    ) -> StoredFile:
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


def get_storage() -> LocalDiskStorage:
    return LocalDiskStorage(storage_root(), upload_max_bytes())
