"""Job kinds. Each handler runs after the venue context is bound."""

from __future__ import annotations

import base64
import uuid
from collections.abc import Callable

from madira.rbac import Capability

Handler = Callable[[dict], dict]

REQUEST_ATTEMPTS = 1
SCHEDULED_ATTEMPTS = 3

KIND_CAPABILITY = {
    "menu.ingest": Capability.EDIT,
    "list.import": Capability.EDIT,
    "sensor.csv": Capability.SENSORS_MANAGE,
    "price_sheet.ingest": Capability.SUPPLIERS_MANAGE,
    "invoice.extract": Capability.PO_WRITE,
    "briefing.build": Capability.RECORDS,
    "reminders.refresh": Capability.RECORDS,
    "pos.sync": Capability.POS_MANAGE,
    "catalog.embed": Capability.FLOOR,
    "catalog.embed_backfill": Capability.FLOOR,
}


def file_args(body: bytes, filename: str, content_type: str | None, **extra) -> dict:
    args = {
        "filename": filename,
        "content_type": content_type or "",
        "body_b64": base64.b64encode(body).decode("ascii") if body else "",
    }
    args.update(extra)
    return args


def _bytes(args: dict) -> bytes:
    raw = args.get("body_b64") or ""
    if not raw:
        return b""
    return base64.b64decode(raw)


def handle_menu(args: dict) -> dict:
    from madira.agents.presenters.menu import with_review
    from madira.domain.menu.service import ingest_menu
    from madira.tenancy import active_venue_id

    menu_key = (args.get("menu_id") or "").strip()
    payload = ingest_menu(
        active_venue_id(),
        filename=args.get("filename") or "",
        body=_bytes(args),
        content_type=args.get("content_type"),
        text=args.get("text") or "",
        url=args.get("url") or "",
        menu_id=uuid.UUID(menu_key) if menu_key else None,
    )
    return with_review(payload)


def handle_list(args: dict) -> dict:
    from madira.domain.lists.csv_import import import_csv
    from madira.tenancy import active_venue_id

    return import_csv(
        active_venue_id(),
        filename=args.get("filename") or "",
        body=_bytes(args),
        content_type=args.get("content_type"),
        confirm=bool(args.get("confirm")),
        name=args.get("name") or "",
    )


def handle_sensor(args: dict) -> dict:
    from madira.domain.sensors.service import preview_csv
    from madira.tenancy import active_venue_id

    return preview_csv(active_venue_id(), args.get("filename") or "readings.csv", _bytes(args))


def handle_price_sheet(args: dict) -> dict:
    from madira.domain.procurement.offers import ingest_price_sheet
    from madira.tenancy import active_venue_id

    return ingest_price_sheet(
        active_venue_id(),
        uuid.UUID(str(args["supplier_id"])),
        filename=args.get("filename") or "",
        body=_bytes(args),
        content_type=args.get("content_type"),
    )


def handle_invoice(args: dict) -> dict:
    from madira.domain.procurement.receiving import upload_invoice
    from madira.tenancy import active_venue_id, current_request

    return upload_invoice(
        active_venue_id(),
        uuid.UUID(str(args["po_id"])),
        filename=args.get("filename") or "invoice",
        content_type=args.get("content_type"),
        body=_bytes(args),
        invoice_number=args.get("invoice_number") or "",
        invoice_date=args.get("invoice_date") or "",
        tax_cents=int(args.get("tax_cents") or 0),
        lines=args.get("lines"),
        actor=current_request(),
    )


def handle_briefing(_args: dict) -> dict:
    from madira.domain.training.briefing import build

    body = build()
    briefing = body.get("briefing") or {}
    return {
        "briefing_id": "" if briefing.get("id") is None else str(briefing.get("id")),
        "status": str(briefing.get("status") or ""),
    }


def handle_reminders(_args: dict) -> dict:
    from madira.domain.reminders.service import list_reminders
    from madira.tenancy import active_venue_id

    body = list_reminders(active_venue_id())
    return {"rules": len(body.get("rules") or []), "reminders": len(body.get("reminders") or [])}


def handle_embed(args: dict) -> dict:
    from madira.domain.embeddings.service import embed_subject
    from madira.tenancy import active_venue_id

    return embed_subject(active_venue_id(), str(args.get("subject_type") or ""), uuid.UUID(str(args["subject_id"])))


def handle_embed_backfill(_args: dict) -> dict:
    from madira.domain.embeddings.service import backfill_venue
    from madira.tenancy import active_venue_id

    return backfill_venue(active_venue_id())


def handle_pos(_args: dict) -> dict:
    from madira.domain.pos.service import sync
    from madira.tenancy import active_venue_id

    body = sync(active_venue_id())
    return {
        "posted": body["posted"],
        "skipped": body["skipped"],
        "unmapped": body["unmapped"],
        "run": body["run"],
    }


HANDLERS: dict[str, Handler] = {
    "menu.ingest": handle_menu,
    "list.import": handle_list,
    "sensor.csv": handle_sensor,
    "price_sheet.ingest": handle_price_sheet,
    "invoice.extract": handle_invoice,
    "briefing.build": handle_briefing,
    "reminders.refresh": handle_reminders,
    "pos.sync": handle_pos,
    "catalog.embed": handle_embed,
    "catalog.embed_backfill": handle_embed_backfill,
}
