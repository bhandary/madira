# Supplier tastings

Supplier tastings drafts a cellar hold with an importer, shows it on a calendar, and prints a `.ics` document. The draft is marked not sent. The same document is available from the tasting URL.

## Sub-features

- `suppliers-seed` lists the seeded importers and distributor.
- `suppliers-draft` delegates to `supplier-scheduler` and renders the schedule form.
- `suppliers-calendar` lists the new tasting.
- `suppliers-ics` shows `BEGIN:VCALENDAR` on the page and from `GET /tastings/{id}/ics`.

## How to get to it (user POV)

- Choose `Suppliers` in the sidebar, or open `http://127.0.0.1:3000/suppliers`. The page heading stays `Supplier tastings`.
- On a narrow viewport, choose `More`, then `Suppliers`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- `[data-testid=suppliers-workbench-submit]` is enabled before the click.
- `GET http://127.0.0.1:8123/suppliers` returns Kermit Lynch Wine Merchant (importer), Skurnik Wines (importer), Bay Area Craft Beer Collective (distributor), and World Sake Imports (importer). Emails are `*.example`.

- **Price sheet.** Open `/suppliers`. Choose `Kermit Lynch Wine Merchant` in `[data-testid=supplier-picker]`. Set `[data-testid=price-sheet-file]` to a CSV:

  ```
  name,sku,unit,case_size,price
  Muscadet Domaine de l'Ecu,W-MUS-01,750ml bottle,12,19.50
  Chateau Nowhere 2015,,750ml bottle,12,30.00
  ```

  Choose `[data-testid=price-sheet-upload]`. `[data-testid=price-sheet-review]` shows `Muscadet Domaine de l'Ecu · USD 19.50 matched` and `Chateau Nowhere 2015 · USD 30.00 unmatched · No catalog product matched this row.` Choose `[data-testid=price-sheet-apply]`. `[data-testid=supplier-offer]` contains `Muscadet` and `USD 19.50`. `[data-testid=price-history]` contains `Muscadet`. Source: `frontend/src/components/SupplierDesk.tsx`.
- **Prompt.** The heading is `Supplier tastings`. `[data-testid=suppliers-workbench-prompt]` is `Schedule a tasting with Kermit Lynch Wine Merchant titled New Loire releases tasting at the Maison Madira cellar. Produce a draft .ics only — do not send.`
- **Run.** Choose `[data-testid=suppliers-workbench-submit]`. `[data-testid=agent-working]` reads `Working…` while the specialist runs. Wait for `[data-testid=delegate-supplier-scheduler]` to show `COMPLETE`. The stream renders `ScheduleForm` and `TastingCalendar`.
- **Draft.** `[data-testid=schedule-form]` reads `New Loire releases tasting`, `DRAFT · NOT SENT`, supplier `Kermit Lynch Wine Merchant`, location `Maison Madira cellar`, and `Draft hold — export .ics, do not send invites.` The time is seven days from the run date, 15:00–17:00. On a run on 2026-11-27 it was `2026-12-04T15:00` to `2026-12-04T17:00`.
- **Calendar and ics.** `[data-testid=tasting-calendar]` lists `New Loire releases tasting` with that supplier and location. `[data-testid=ics-block]` starts with `BEGIN:VCALENDAR`, includes `METHOD:PUBLISH`, `SUMMARY:New Loire releases tasting`, and `(draft only — not sent)`. It does not contain `mailto:`.
- **Read back.** `curl -sS http://127.0.0.1:8123/tastings` returns JSON with a `tastings` array. Take that row's `id` (a UUID) and `curl -sS -D- http://127.0.0.1:8123/tastings/<id>/ics`. The response is `200`, `content-type: text/calendar; charset=utf-8`, and the same `BEGIN:VCALENDAR` body.
- **Proof.** Screenshot the draft badge, the `.ics` block, and the calendar entry.

## Gotchas

- Tasting ids are UUIDs. `GET /tastings/1/ics` is 422, not a lookup of the first row.
- `Run specialists` is disabled until the page connects to its thread. Wait for it to be enabled, then click. Before the run the rail reads `No specialists engaged yet.`
- The start time is computed at run time (observed as seven days ahead at 15:00). Assert the title, the draft badge, and `BEGIN:VCALENDAR`, not one frozen timestamp, unless you just read it back.
- Nothing in the response or the `.ics` is an email send. There is no `mailto:` and the badge says `DRAFT · NOT SENT`. This run did not have a mailbox to watch.
- A second run with the same title updates that tasting rather than proving a new row. Compare `id` if you need to tell them apart.
