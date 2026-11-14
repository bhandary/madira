# Inventory

Inventory shows the seeded cellar, lets the floor change a SKU's on-hand count immediately, and then drafts purchase orders. The orders are marked draft and not sent.

## Sub-features

- `inventory-cellar` loads the seeded rows and a low-stock count.
- `inventory-adjust` writes on-hand for one SKU before the specialist runs.
- `inventory-draft` delegates to `inventory-purchasing` and renders draft orders.
- `inventory-stored` keeps those draft orders for a later GET.

## How to get to it (user POV)

- Choose `Inventory` in the sidebar, or open `http://127.0.0.1:3000/inventory`.
- On a narrow viewport, choose `Sections`, then `Inventory`. Opening `Sections` on this page is what showed `Supplier tastings`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- Note `W-MUS-01` before changing it. On a fresh seed, `GET /inventory` returns 15 items, 9 with `low` true, and `W-MUS-01` (`Muscadet Domaine de l'Ecu`) at `on_hand` 4, `par` 12, supplier `Kermit Lynch Wine Merchant`.

- **Loaded line.** Open `/inventory`. The heading is `Inventory & purchasing`. Wait until the status line is `9 SKUs under par in the seeded cellar.` The line `Loading cellar…` is the earlier state.
- **Adjust.** Fill `[data-testid=inv-sku]` with `W-MUS-01` and `[data-testid=inv-qty]` with `1`. Choose `[data-testid=inv-adjust]`. Wait for `PATCH /madira-api/inventory/W-MUS-01`. `GET http://127.0.0.1:8123/inventory` then shows that SKU at `on_hand` 1, `low` true, `reorder_qty` 11. `[data-testid=inventory-workbench-prompt]` reads `Set on-hand for W-MUS-01 to 1, then draft purchase orders for every SKU below par. Do not transmit orders.`
- **Run.** Choose `[data-testid=inventory-workbench-submit]` after it is hydrated. Wait for `[data-testid=delegate-inventory-purchasing]` to show `COMPLETE`.
- **Surfaces.** `[data-testid=stock-alerts]` lists the low SKUs. `[data-testid=inventory-table]` shows `W-MUS-01` on hand `1` with a `low` badge. `[data-testid=purchase-order-table]` contains `DRAFT · NOT SENT` for Bay Area Craft Beer Collective, World Sake Imports, Skurnik Wines, and Kermit Lynch Wine Merchant.
- **Read back.** `curl -sS http://127.0.0.1:8123/purchase-orders` returns four orders, each `status` `draft`, suppliers `Kermit Lynch Wine Merchant`, `Skurnik Wines`, `World Sake Imports`, and `Bay Area Craft Beer Collective`.
- **Restore.** `curl -sS -X PATCH http://127.0.0.1:8123/inventory/W-MUS-01 -H 'Content-Type: application/json' -d '{"on_hand":4}'` returns that SKU at `on_hand` 4 again.
- **Proof.** Screenshot the alerts, the table row for `W-MUS-01`, and the draft orders.

## Gotchas

- `Adjust stock now` writes immediately. It does not wait for `Run specialists`.
- The low-stock count can stay `9` after moving `W-MUS-01` from 4 to 1, because that SKU was already under par.
- Draft orders remain in the database after the on-hand value is restored. `make clean` deletes the sqlite file.
- An unknown SKU surfaces `[data-testid=inventory-error]`. This drive used `W-MUS-01` and did not see that alert.
