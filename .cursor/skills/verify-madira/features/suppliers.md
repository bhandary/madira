# Supplier tastings

Supplier tastings drafts a cellar hold with an importer, shows it on a calendar, and prints a `.ics` document. The draft is marked not sent. The same document is available from the tasting URL.

## Sub-features

- `suppliers-seed` lists the seeded importers and distributor.
- `suppliers-draft` delegates to `supplier-scheduler` and renders the schedule form.
- `suppliers-calendar` lists the new tasting.
- `suppliers-ics` shows `BEGIN:VCALENDAR` on the page and from `GET /tastings/{id}/ics`.

## How to get to it (user POV)

- Choose `Supplier tastings` in the sidebar, or open `http://127.0.0.1:3000/suppliers`.
- On a narrow viewport, choose `Sections`, then `Supplier tastings`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- `[data-testid=suppliers-workbench-submit]` is hydrated before the click.
- `GET http://127.0.0.1:8123/suppliers` returns Kermit Lynch Wine Merchant (importer), Skurnik Wines (importer), Bay Area Craft Beer Collective (distributor), and World Sake Imports (importer). Emails are `*.example`.

- **Prompt.** Open `/suppliers`. The heading is `Supplier tastings`. `[data-testid=suppliers-workbench-prompt]` is `Schedule a tasting with Kermit Lynch Wine Merchant titled New Loire releases tasting at the Maison Madira cellar. Produce a draft .ics only — do not send.`
- **Run.** Choose `[data-testid=suppliers-workbench-submit]`. Wait for `[data-testid=delegate-supplier-scheduler]` to show `COMPLETE`. The `POST /madira-api/agent/run` body has `demo_mode` true and components `ScheduleForm` and `TastingCalendar`.
- **Draft.** `[data-testid=schedule-form]` reads `New Loire releases tasting`, `DRAFT · NOT SENT`, supplier `Kermit Lynch Wine Merchant`, location `Maison Madira cellar`, and `Draft hold — export .ics, do not send invites.` On this run the time was `2026-11-21T15:00` to `2026-11-21T17:00` (seven days from the run, 15:00–17:00).
- **Calendar and ics.** `[data-testid=tasting-calendar]` lists `New Loire releases tasting` with that supplier and location. `[data-testid=ics-block]` starts with `BEGIN:VCALENDAR`, includes `METHOD:PUBLISH`, `SUMMARY:New Loire releases tasting`, and `(draft only — not sent)`. It does not contain `mailto:`.
- **Read back.** `curl -sS http://127.0.0.1:8123/tastings` returns JSON with a `tastings` array. Take that row's `id` (it was `1` on a fresh database) and `curl -sS -D- http://127.0.0.1:8123/tastings/<id>/ics`. The response is `200`, `content-type: text/calendar`, and the same `BEGIN:VCALENDAR` body.
- **Proof.** Screenshot the draft badge, the `.ics` block, and the calendar entry.

## Gotchas

- Clicking `Run specialists` before hydration navigates to `/suppliers?` and leaves `No specialists engaged yet.` Wait for a `__react` property on the button, then click.
- The start time is computed at run time (observed as seven days ahead at 15:00). Assert the title, the draft badge, and `BEGIN:VCALENDAR`, not one frozen timestamp, unless you just read it back.
- Nothing in the response or the `.ics` is an email send. There is no `mailto:` and the badge says `DRAFT · NOT SENT`. This run did not have a mailbox to watch.
- A second run with the same title updates that tasting rather than proving a new row. Compare `id` if you need to tell them apart.
