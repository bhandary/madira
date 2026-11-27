# Tasting sessions

Tasting sessions are planned on `/tastings`, separate from the supplier workbench. A session can hold scored samples and a calendar file that downloads as `.ics`.

## Sub-features

- `tasting-plan` creates a session for a supplier.
- `tasting-score` records a sample score.
- `tasting-ics` downloads the calendar. Nothing is emailed.

## How to get to it (user POV)

- Choose `Tastings` in the sidebar or in `More`, or open `http://127.0.0.1:3000/tastings`.
- Source: `frontend/src/app/tastings/page.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. `[data-testid=tasting-plan]` is enabled.

- **Plan.** Open `/tastings`. The heading is `Tasting sessions`. Choose `Kermit Lynch Wine Merchant` in `[data-testid=tasting-supplier]`. Fill `[data-testid=tasting-title]` with `Phone Loire tasting` and `[data-testid=tasting-when]` with `2026-12-01T15:00`. Choose `[data-testid=tasting-plan]`. `[data-testid=tasting-session-title]` is `Phone Loire tasting`.
- **Score.** Choose `[data-testid=tasting-add-sample]`. Fill `[data-testid=sample-score]` with `80` and choose `[data-testid=sample-score-save]`. Wait until `[data-testid=sample-score-value]` is `Score 80`. A click that is not followed by that wait can still show `No score`.
- **Calendar.** Choose `[data-testid=tasting-ics]`. The download is `text/calendar` and the body contains `BEGIN:VCALENDAR` and `DTSTART:20261201T150000Z`.
- **Read back.** `curl -sS http://127.0.0.1:8123/tastings` includes `Phone Loire tasting`.
- **Proof.** Screenshot the session title and both scores.

## Gotchas

- The supplier workbench on `/suppliers` still drafts an unsent `.ics` for a different flow. This page is the session planner.
- A buy on a scored sample (`[data-testid=sample-buy]`) creates a draft purchase order and links it with `[data-testid=sample-po]`. That order then shows on `/purchasing`. It is a second recipe, not required to prove the calendar.
