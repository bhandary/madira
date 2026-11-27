# Inventory

Inventory shows the seeded cellar, lets the floor change a SKU's on-hand count immediately, and then drafts purchase orders. The orders are marked draft and not sent. The same page is the cellar ledger: locations, bins, a QR label, movements, transfers, and storage-zone readings.

## Sub-features

- `inventory-cellar` loads the seeded rows and a low-stock count.
- `inventory-adjust` writes on-hand for one SKU before the specialist runs.
- `inventory-draft` delegates to `inventory-purchasing` and renders draft orders.
- `inventory-stored` keeps those draft orders for a later GET.
- `inventory-ledger` filters by location, posts a receive, and transfers a bottle without changing the SKU total.
- `inventory-bins` creates a bin and shows its QR payload.
- `inventory-zones` logs an out-of-range reading and acknowledges the excursion.

## How to get to it (user POV)

- Choose `Inventory` in the sidebar, or open `http://127.0.0.1:3000/inventory`.
- On a narrow viewport, choose the `Cellar` tab (`/inventory`). Opening `More` on this page shows `Suppliers`, `Tastings`, `Sourcing`, `POS`, `Sensors`, `Audit`, `Usage`, `Records`, and `Settings`. `Purchasing` and `Phone count` are not in that sheet. Phone count is `[data-testid=open-count]` on this page.
- `Count on a phone` (`[data-testid=open-count]`) opens [Phone count](./counts.md).

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- Note `W-MUS-01` before changing it. On a fresh seed, `GET /inventory` returns 15 items, 9 with `low` true, and `W-MUS-01` (`Muscadet Domaine de l'Ecu`) at `on_hand` 4, `par` 12, `reorder_qty` 8, supplier `Kermit Lynch Wine Merchant`, `unit_cost` 1800 (cents).
- Do the ledger steps after the restore, or put the on-hand count back before a later recipe that expects 4.

- **Search.** On `/inventory`, fill `[data-testid=catalog-search]` with `Barolo` and choose `[data-testid=catalog-search-submit]`. `[data-testid=catalog-search-mode]` is `Ranked by taste similarity.` when the local embeddings are ready, and `Matched the catalog words.` when they are not. A `[data-testid=catalog-hit]` has `data-name` `Barolo G.D. Vajra 2019`. Source: `frontend/src/components/CatalogSearch.tsx`.
- **Loaded line.** Open `/inventory`. The heading is `Inventory & purchasing`. Wait until the status line is `9 SKUs under par in the seeded cellar.` The line `Loading cellar…` is the earlier state. `[data-testid=cellar-board]` is visible. `[data-testid=storage-zones]` lists `Main Cellar` and `Bar & Cold Box`, each `[data-testid=zone-status]` `OK`.
- **Adjust.** Fill `[data-testid=inv-sku]` with `W-MUS-01` and `[data-testid=inv-qty]` with `1`. Choose `[data-testid=inv-adjust]`. Wait for `PATCH /madira-api/inventory/W-MUS-01`. `GET http://127.0.0.1:8123/inventory` then shows that SKU at `on_hand` 1, `low` true, `reorder_qty` 11. `[data-testid=inventory-workbench-prompt]` reads `Set on-hand for W-MUS-01 to 1, then draft purchase orders for every SKU below par. Do not transmit orders.`
- **Run.** Choose `[data-testid=inventory-workbench-submit]` once it is enabled. Wait for `[data-testid=delegate-inventory-purchasing]` to show `COMPLETE`.
- **Surfaces.** `[data-testid=stock-alerts]` lists the low SKUs. `[data-testid=inventory-table]` shows `W-MUS-01` on hand `1` with a `low` badge. `[data-testid=purchase-order-table]` contains `DRAFT · NOT SENT` for Bay Area Craft Beer Collective, World Sake Imports, Skurnik Wines, and Kermit Lynch Wine Merchant.
- **Read back.** `curl -sS http://127.0.0.1:8123/purchase-orders` returns four orders, each `status` `draft`, suppliers `Kermit Lynch Wine Merchant`, `Skurnik Wines`, `World Sake Imports`, and `Bay Area Craft Beer Collective`. These are the bottle-count drafts. Case-rounded orders live on [Purchasing](./purchasing.md) under `GET /procurement/orders`.
- **Restore.** `curl -sS -X PATCH http://127.0.0.1:8123/inventory/W-MUS-01 -H 'Content-Type: application/json' -d '{"on_hand":4}'` is 200. The body is the cellar snapshot (`items`, `alerts`, `locations`, `a2ui_operations`), not that SKU alone. The `W-MUS-01` row inside `items` is `on_hand` 4, `low` true, and `reorder_qty` 8.
- **Locations.** On the stock tab, `[data-testid=sku-row][data-sku=W-MUS-01]` shows on-hand `4` on a fresh seed. Its location quantities are Main Bar `2`, Main Cellar `0`, and Walk-In Cooler `2`. Choose the `Main Cellar` `[data-testid=location-pill]`. Every visible `[data-testid=sku-row]` has a Main Cellar quantity that is not 0, and `W-MUS-01` is not among them until a receive lands there. Choose `All locations` again.
- **Bin.** Choose `[data-testid=cellar-tab-places]`. Select `Main Cellar` in `[data-testid=bin-location]`, fill `[data-testid=bin-code]` with a new code such as `E2E-1`, fill `[data-testid=bin-label]` with `Verify bin`, and choose `[data-testid=bin-create]`. The new `[data-testid=bin-row]` is visible. Choose `[data-testid=bin-view-qr]`. `[data-testid=bin-qr]` contains an `svg`, and `[data-testid=bin-qr-payload]` contains `madira:bin:` and that code. `GET /inventory/bins` includes the code.
- **Movement.** Choose `[data-testid=cellar-tab-stock]`. Note the Muscadet on-hand and Main Cellar quantity. Select `W-MUS-01`, movement `receive`, quantity `1.5`, location `Main Cellar`, and a unique reason. Choose `[data-testid=movement-submit]`. On-hand and the Main Cellar quantity each rise by 1.5. Choose `[data-testid=cellar-tab-ledger]`. A `[data-testid=movement-row]` for `W-MUS-01` contains the reason and `1.5`.
- **Transfer.** Back on the stock tab, transfer `1` of `W-MUS-01` from `Main Cellar` to `Main Bar`. On-hand stays the same. Main Cellar drops by 1 and Main Bar rises by 1.
- **Zone.** On `Main Cellar`'s `[data-testid=zone-card]`, fill `[data-testid=zone-temp]` with `22` and `[data-testid=zone-humidity]` with `80`. Choose `[data-testid=zone-record]`. `[data-testid=zone-status]` becomes `Excursion` and `[data-testid=affected-sku]` lists at least one SKU. Choose `[data-testid=zone-acknowledge]`. `GET /inventory/excursions` includes that zone. Log `13` and `68` on the same card to put the status back to `OK` when a later recipe expects a quiet cellar.
- **Proof.** Screenshot the alerts, the table row for `W-MUS-01`, the draft orders, the QR payload, and the excursion badge.

## Gotchas

- `Adjust stock now` writes immediately. It does not wait for `Run specialists`.
- The low-stock count can stay `9` after moving `W-MUS-01` from 4 to 1, because that SKU was already under par.
- Draft orders remain in the database after the on-hand value is restored. `make clean` deletes the sqlite file. It does not delete `backend/data/storage`.
- An unknown SKU shows nothing. `Adjust stock now` with `NOPE-00` and quantity `1` sends `PATCH /inventory/NOPE-00`. The response is 404 `{"detail":"unknown sku NOPE-00"}`, and `[data-testid=inventory-error]` does not appear. `patchStock` in `frontend/src/lib/api.ts` returns `res.json()` without checking the status, so the page's `catch` never runs. Do not use that alert as proof of a rejected SKU; check the PATCH status. This is a product defect. Leave it recorded. Do not describe the alert as if it appeared.
- `Adjust stock now` posts the whole delta to Main Cellar (`apply_count` in `backend/madira/domain/inventory/ledger.py`). Dropping `W-MUS-01` from 4 to 1 leaves Main Cellar at `-3` while Main Bar stays `2` and Walk-In Cooler stays `2`. The SKU `on_hand` is `1`. The negative location is a product defect. The passing check for the adjust is the SKU `on_hand`, not a non-negative split.
- A receive of `1.5` is a tenth, not a whole bottle. Read `on_hand` as a number, not only as the integer 4.
- `Print label` opens a new window and calls `print()`. The payload on the page is the proof. Do not require a printer dialog.
