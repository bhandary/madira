"""Encrypt LLM API keys at rest with Fernet.

`MADIRA_SECRET_KEY` may be a Fernet key (`Fernet.generate_key()`) or any other
secret string, which is stretched with SHA-256 into a Fernet key.

If `MADIRA_SECRET_KEY` is unset, a key is generated once and written to
`backend/data/.madira_secret` (mode 0600). That file is a local dev fallback
and sits next to the SQLite database. Set `MADIRA_SECRET_KEY` anywhere the
database is shared or deployed. Saving a key fails with a clear error if the
fallback file cannot be created.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from madira.config import DATA_DIR

SECRET_FILE = DATA_DIR / ".madira_secret"
logger = logging.getLogger("madira")
_logged_fallback = False


def _is_fernet_key(raw: str) -> bool:
    try:
        Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError):
        return False
    return True


def _derive(raw: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())


def fernet_key_bytes() -> bytes:
    raw = os.environ.get("MADIRA_SECRET_KEY", "").strip()
    if not raw:
        raw = _dev_fallback_secret()
    if _is_fernet_key(raw):
        return raw.encode("utf-8")
    return _derive(raw)


def load_fernet() -> Fernet:
    return Fernet(fernet_key_bytes())


def _dev_fallback_secret() -> str:
    global _logged_fallback
    path = SECRET_FILE
    try:
        if path.is_file():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                _warn_fallback(path)
                return existing
        path.parent.mkdir(parents=True, exist_ok=True)
        generated = Fernet.generate_key().decode("utf-8")
        path.write_text(generated + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _warn_fallback(path)
        return generated
    except OSError as exc:
        raise RuntimeError(
            "Set MADIRA_SECRET_KEY to encrypt LLM API keys. "
            f"The dev fallback file {path} could not be created: {exc}"
        ) from exc


def _warn_fallback(path) -> None:
    global _logged_fallback
    if _logged_fallback:
        return
    _logged_fallback = True
    logger.warning(
        "MADIRA_SECRET_KEY is unset; using the dev fallback at %s. "
        "Set MADIRA_SECRET_KEY outside local development.",
        path,
    )


def encrypt_secret(plaintext: str) -> str:
    return load_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return load_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Saved LLM key could not be decrypted. "
            "MADIRA_SECRET_KEY does not match the key that encrypted it."
        ) from exc
