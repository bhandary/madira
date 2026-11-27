# Phone count

Phone count starts a count at a location, queues lines while the browser is offline, syncs them, and asks for approval when the counted quantity differs from the book. The same page proposes a new par from the last 30 days of depletion.

## Sub-features

- `count-start` opens a session at Main Cellar.
- `count-offline` queues two lines with no network, then syncs them.
- `count-approve` submits the variance and posts a count adjustment.
- `count-par` generates a par proposal and accepts it.

## How to get to it (user POV)

- Choose `Phone count` in the sidebar, or open `http://127.0.0.1:3000/inventory/count`.
- On a narrow viewport, choose `More`, then `Phone count`. From Inventory, `Count on a phone` is the same page.
- The heading is `Count`. The page is laid out for 390×844.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- `[data-testid=count-location]` lists `Main Cellar`.
- Offline queueing needs Playwright `context.setOffline(true)`. curl cannot hold the line on the phone.
- Approving a count writes the counted quantity as the new on-hand at that location. Count `S-TOK-01` if you need to leave `W-MUS-01` alone. Read the book quantity first if the assertion is the delta.

- **Start.** Open `/inventory/count`. The heading is `Count`. Choose `Main Cellar` in `[data-testid=count-location]` and `[data-testid=count-start]`. `[data-testid=count-sheet]` is visible. `[data-testid=count-sku]` includes an option `S-TOK-01`.
- **Queue.** Set the browser context offline. Select `S-TOK-01`. Choose `[data-testid=count-plus-tenth]`, `[data-testid=count-minus-tenth]`, then `[data-testid=count-plus-tenth]` again. `[data-testid=count-qty]` is `0.1`. Choose `[data-testid=count-save]`. `[data-testid=queued-offline]` reads `Queued offline (1)`. The count sheet does not show the line yet.
- **Sync.** Set the context online. Choose `[data-testid=count-sync]`. The queued notice is gone. `[data-testid=count-line]` contains `S-TOK-01`.
- **Submit.** Choose `[data-testid=count-submit]`. `[data-testid=variance-report]` is visible. The `S-TOK-01` `[data-testid=variance-line]` contains `0.1`. On a fresh seed that line's expected quantity is `1`: the bottle in Main Cellar, not the SKU total of `2` (the other bottle is at Main Bar). Choose `[data-testid=count-approve]`. `[data-testid=count-approved]` is visible.
- **Read back.** `curl -sS http://127.0.0.1:8123/inventory/counts` includes that session with `status` `approved`. `GET /inventory/movements` includes a row with `movement_type` `count_adjustment` for `S-TOK-01`. On `/inventory`, the ledger tab shows a `[data-testid=movement-row][data-type=count_adjustment]`.
- **Par.** On `/inventory/count`, choose `[data-testid=par-generate]`. A `[data-testid=par-proposal]` is visible with `data-sku` and `data-proposed`. On a fresh seed, `B-KRK-01` (3 Fonteinen Oude Kriek, depletion 10) proposes par `4` from par `12`: ceil of the daily rate times 7 lead days and 4 safety days. Choose `[data-testid=par-accept]` on one card. That card is gone. On `/inventory`, `[data-testid=sku-row][data-sku=<that sku>]` `[data-testid=sku-par]` equals `data-proposed`. `GET /inventory/par-proposals` no longer lists it as `pending`. Accepting a proposal that lifts a SKU to or above its on-hand drops the low-stock count.
- **Proof.** Screenshot the queued notice, the variance line, and the accepted par gone from the list.

## Gotchas

- `Save count` while online posts immediately and never shows `Queued offline`. The offline assertion needs `setOffline` before the save.
- Submit with a non-empty offline queue shows `Sync the offline queue before submitting.` and does not post the session.
- A second start while one session is `in_progress` shows `Resume <location>` (`[data-testid=count-resume]`). Resume that session instead of expecting a second empty sheet for the same location.
- Accepting a par changes the cellar. Reject (`[data-testid=par-reject]`) leaves the current par in place.
- The quantity field allows tenths. `+0.1` three times is `0.3`, not `0.30000000000000004`, because the control rounds to one decimal.
