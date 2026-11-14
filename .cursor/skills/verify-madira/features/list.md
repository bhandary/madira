# List curation

List curation asks for a cellar budget and a target multiple, then shows a summary and a beverage table. The rail names List Curator. The saved list is readable from `GET /lists`.

## Sub-features

- `list-inputs` sets the budget and the target multiple used in the prompt.
- `list-run` delegates to `list-curator` and renders the summary and table.
- `list-stored` keeps that list for a later GET.

## How to get to it (user POV)

- Choose `List curation` in the sidebar, or open `http://127.0.0.1:3000/list`.
- On a narrow viewport, choose `Sections`, then `List curation`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- The submit button is hydrated.

- **Set the numbers.** Open `/list`. The heading is `List curation`. Fill `[data-testid=list-budget]` with `12000` and `[data-testid=list-margin]` with `3.2`. `[data-testid=list-workbench-prompt]` reads `Curate a wine, beer, spirit, and sake list to complement the Maison Madira autumn menu. Budget $12000. Target pour/bottle margin 3.2x. Show coverage by category/region/style/price, gaps, and cost/margin math.`
- **Run.** Choose `[data-testid=list-workbench-submit]`. Wait for `[data-testid=delegate-list-curator]` to show `COMPLETE`.
- **Summary.** `[data-testid=list-summary]` reads budget `$12,000`, spent `$5,198`, remaining `$6,802`, target multiple `3.2x`, then `wine 8 · $3,432`, `beer 4 · $478`, `spirit 4 · $232`, `sake 3 · $1,056`, and `Gaps: none — categories covered`.
- **Table.** `[data-testid=beverage-list-table]` has columns Category, Name, Region / style, Cost, Pour, Bottle, Margin. The first row is wine `Muscadet Sèvre-et-Maine Sur Lie`.
- **Read back.** `curl -sS http://127.0.0.1:8123/lists` returns a list named `Maison Madira autumn list` with `budget` 12000, `target_margin` 3.2, and `item_count` 19.
- **Proof.** Screenshot the summary and the table after the curator row is `COMPLETE`.

## Gotchas

- The currency text uses a thousands separator (`$12,000`, `$5,198`). Assert the visible summary, not the raw prompt numbers alone.
- Each run inserts another beverage list. Read the newest row, or the row whose budget and margin match the prompt.
