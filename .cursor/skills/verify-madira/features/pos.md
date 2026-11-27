# POS

POS connects a register, maps a sale to a cellar SKU, and posts that sale so the on-hand count drops. Demo mode uses the built-in register. Square is the other adapter and needs Square credentials this baseline does not set.

## Sub-features

- `pos-demo` connects the demo register.
- `pos-map` saves the Muscadet variation onto `W-MUS-01`.
- `pos-sync` posts the sale and the cellar count falls by 1.

## How to get to it (user POV)

- Choose `POS` in the sidebar or in `More`, or open `http://127.0.0.1:3000/pos`.
- Source: `frontend/src/app/pos/page.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- Read `W-MUS-01` `[data-testid=sku-on-hand]` on `/inventory` before the sync.

- **Connect.** Open `/pos`. The heading is `POS`. If `[data-testid=pos-connect]` is visible, choose `Connect the demo register`. `[data-testid=pos-connected]` is then visible.
- **Map.** On `[data-testid=pos-item][data-variation=demo-var-muscadet]`, choose `Save mapping`. The button is enabled before the click.
- **Sync.** Choose `[data-testid=pos-sync]`. The first `[data-testid=pos-run]` reads `completed · posted 1 · skipped 0 · unmapped 1` on the demo register (one mapped Muscadet sale and one unmapped line).
- **Cellar.** On `/inventory`, `W-MUS-01` `[data-testid=sku-on-hand]` is 1 less than the number you read.
- **Read back.** `curl -sS http://127.0.0.1:8123/pos/status` reports the demo connection. `GET /pos/runs` includes the posted run.
- **Proof.** Screenshot the posted run and the inventory on-hand after the sync.

## Gotchas

- Square connect is not part of this baseline. Leave `SQUARE_ACCESS_TOKEN` unset. The demo button is the path.
- Run this after any recipe that needs the seeded Muscadet on-hand, or note the new number. The drop is 1 bottle from the demo sale.
