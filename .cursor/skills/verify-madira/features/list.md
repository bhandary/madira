# List curation

List curation asks for a cellar budget and a target multiple, then shows a summary and a beverage table. The rail names List Curator. The saved list is readable from `GET /lists`.

## Sub-features

- `list-inputs` sets the budget and the target multiple used in the prompt.
- `list-run` delegates to `list-curator` and renders the summary and table.
- `list-stored` keeps that list for a later GET.
- `list-import` previews `fixtures/sample_list.csv`, then confirms it onto the list.

## How to get to it (user POV)

- Choose `List curation` in the sidebar, or open `http://127.0.0.1:3000/list`.
- On a narrow viewport, choose the `List` tab.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- The submit button is enabled.

- **Set the numbers.** Open `/list`. The heading is `List curation`. Fill `[data-testid=list-budget]` with `12000` and `[data-testid=list-margin]` with `3.2`. `[data-testid=list-workbench-prompt]` reads `Curate a wine, beer, spirit, and sake list to complement the Maison Madira autumn menu. Budget $12000. Target pour/bottle margin 3.2x. Show coverage by category/region/style/price, gaps, and cost/margin math.`
- **Run.** Choose `[data-testid=list-workbench-submit]`. Wait for `[data-testid=delegate-list-curator]` to show `COMPLETE`.
- **Summary.** `[data-testid=list-summary]` reads budget `$12,000`, spent `$5,198`, remaining `$6,802`, target multiple `3.2x`, then `wine 8 · $3,432`, `beer 4 · $478`, `spirit 4 · $232`, `sake 3 · $1,056`, and `Gaps: none — categories covered`.
- **Table.** `[data-testid=beverage-list-table]` has columns Category, Name, Region / style, Cost, Pour, Bottle, Margin. The first row is wine `Muscadet Sèvre-et-Maine Sur Lie`.
- **Read back.** `curl -sS http://127.0.0.1:8123/lists` returns a list named `Maison Madira autumn list` with `budget` 1200000, `currency` `USD`, `target_margin` 3.2, and `item_count` 19. Money is in cents: the first item, `Muscadet Sèvre-et-Maine Sur Lie`, has `cost` 1800, `pour_price` 1600, and `bottle_price` 6200.
- **Proof.** Screenshot the summary and the table after the curator row is `COMPLETE`.
- **Import.** Stay on `/list`. Choose `[data-testid=list-import-file]` and the repo file `fixtures/sample_list.csv`. Choose `[data-testid=list-import-preview]`. `[data-testid=list-import-summary]` counts matched, new products, new variants, and errors. `[data-testid=list-import-preview-table]` shows `Muscadet Domaine de l'Ecu` as `Matched` (it is already in the cellar). `Chablis Premier Cru Vaillons` is `New product` the first time and `Matched` if that bottle was imported before. Choose `[data-testid=list-import-confirm]`. `[data-testid=list-import-entries]` then shows those names, including `Barolo` and `Kölsch`.
- **Read the import back.** `curl -sS http://127.0.0.1:8123/lists` includes a list whose `source_filename` is `sample_list.csv`. Money is in cents. `Chablis Premier Cru Vaillons` has `bottle_price` 9600, `pour_price` 2200, and `cost` 3400. `Kölsch` has `cost` 240.

## Gotchas

- The currency text uses a thousands separator (`$12,000`, `$5,198`). Assert the visible summary, not the raw prompt numbers alone. `GET /lists` stores money in cents, so `$12,000` is `budget` 1200000.
- Each run inserts another beverage list. Read the newest row, or the row whose budget and margin match the prompt.
