"""Opt-in delivery for a purchase order that is already in the document vault.

The default adapter writes nothing to the network. A later provider can
register itself with ``register_po_email_adapter`` and is used only when
``MADIRA_PO_EMAIL_ENABLED`` is true and ``MADIRA_PO_EMAIL_ADAPTER`` names it.
Until that registration exists, the flag still archives through the vault.
"""

from __future__ import annotations

import os
from typing import Protocol


class POEmailAdapter(Protocol):
    sent_via: str

    def deliver(self, *, po_number: str, pdf: bytes, recipient: str | None = None) -> str:
        """Return a delivery reference. Do not send mail unless this adapter is the opt-in one."""


class VaultArchiveEmailAdapter:
    """Record that the PDF lives in the vault. No SMTP, no HTTP, no inbox."""

    sent_via = "vault_archive"

    def deliver(self, *, po_number: str, pdf: bytes, recipient: str | None = None) -> str:
        del pdf, recipient
        number = (po_number or "").strip() or "draft"
        return f"vault-archive:{number}"


_REGISTRY: dict[str, type[VaultArchiveEmailAdapter]] = {}


def register_po_email_adapter(name: str, adapter: type[VaultArchiveEmailAdapter]) -> None:
    """Hook for a future SMTP or provider adapter. Nothing is registered at launch."""

    label = (name or "").strip()
    if not label:
        raise ValueError("adapter name is required")
    _REGISTRY[label] = adapter


def email_enabled() -> bool:
    return os.environ.get("MADIRA_PO_EMAIL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def get_po_email_adapter() -> POEmailAdapter:
    if email_enabled():
        name = os.environ.get("MADIRA_PO_EMAIL_ADAPTER", "").strip()
        factory = _REGISTRY.get(name)
        if factory is not None:
            return factory()
    return VaultArchiveEmailAdapter()
