"""Admin gate for Settings. The password is compared in constant time and is not stored.

A successful sign-in returns an HMAC token (8 hours). The token dies when the
password or `MADIRA_SECRET_KEY` changes. If `MADIRA_ADMIN_PASSWORD` is unset,
settings reads and writes are refused.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

TOKEN_TTL_SECONDS = 8 * 60 * 60

UNSET_MESSAGE = (
    "Set MADIRA_ADMIN_PASSWORD to manage LLM settings. "
    "Add it to the environment and restart the backend."
)


def admin_password() -> str:
    return os.environ.get("MADIRA_ADMIN_PASSWORD", "")


def admin_configured() -> bool:
    return admin_password() != ""


def passwords_match(provided: str, expected: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(provided.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


def check_password(provided: str) -> bool:
    expected = admin_password()
    if expected == "":
        return False
    return passwords_match(provided, expected)


def _signing_key() -> bytes:
    from madira.crypto import fernet_key_bytes

    return hashlib.sha256(b"madira-admin-v1" + fernet_key_bytes()).digest()


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _password_tag() -> str:
    return hashlib.sha256(admin_password().encode("utf-8")).hexdigest()[:16]


def issue_admin_token(ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    payload = json.dumps(
        {"exp": int(time.time()) + ttl_seconds, "pw": _password_tag()},
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    return _b64e(payload) + "." + _b64e(signature)


def verify_admin_token(token: str) -> bool:
    if not admin_configured() or not token or "." not in token:
        return False
    payload_b64, signature_b64 = token.split(".", 1)
    try:
        payload = _b64d(payload_b64)
        signature = _b64d(signature_b64)
        expected = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
        if len(signature) != len(expected) or not hmac.compare_digest(signature, expected):
            return False
        data = json.loads(payload.decode("utf-8"))
        if int(data["exp"]) < time.time():
            return False
        tag = str(data.get("pw", ""))
        current = _password_tag()
        if len(tag) != len(current):
            return False
        return hmac.compare_digest(tag, current)
    except (ValueError, KeyError, json.JSONDecodeError, TypeError):
        return False
