# List curation

List curation asks for a cellar budget and a target multiple, then shows a summary and a beverage table. The rail names List Curator. The saved list is readable from `GET /lists`. The same page imports `fixtures/sample_list.csv` onto the catalog and drafts a tasting note and a service card for one of the new bottles.

## Sub-features

- `list-inputs` sets the budget and the target multiple used in the prompt.
- `list-run` delegates to `list-curator` and renders the summary and table.
- `list-stored` keeps that list for a later GET.
- `list-import` previews `fixtures/sample_list.csv`, then confirms it onto the list.
- `list-catalog` reads the products that import created.
- `list-notes` drafts, edits, and approves a tasting note and a service card.

## How to get to it (user POV)

- Choose `List curation` in the sidebar, or open `http://127.0.0.1:3000/list`.
- On a narrow viewport, choose the `List` tab.
- Import and notes sit under the workbench in `[data-testid=list-import]`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- The submit button is enabled.
- Import and notes do not need a specialist run. Do them on a fresh database, before a second import of the same file. The seeded catalog already contains a Chablis from the same producer, so the CSV row is a new variant, not a new product.

- **Set the numbers.** Open `/list`. The heading is `List curation`. Fill `[data-testid=list-budget]` with `12000` and `[data-testid=list-margin]` with `3.2`. `[data-testid=list-workbench-prompt]` reads `Curate a wine, beer, spirit, and sake list to complement the Maison Madira autumn menu. Budget $12000. Target pour/bottle margin 3.2x. Show coverage by category/region/style/price, gaps, and cost/margin math.`
- **Run.** Choose `[data-testid=list-workbench-submit]`. Wait for `[data-testid=delegate-list-curator]` to show `COMPLETE`.
- **Summary.** `[data-testid=list-summary]` shows budget `$12,000`, spent `$5,198`, remaining `$6,802`, target multiple `3.2x`, then the chips `wine 8 · $3,432`, `beer 4 · $478`, `spirit 4 · $232`, and `sake 3 · $1,056`, then `Gaps: none — categories covered`. Kickers and badges are styled uppercase, so the visible text is `BUDGET $12,000` and `WINE 8 · $3,432` (and the same for beer, spirit, and sake).
- **Table.** `[data-testid=beverage-list-table]` has columns Category, Name, Region / style, Cost, Pour, Bottle, Margin. The first row is wine `Muscadet Sèvre-et-Maine Sur Lie`.
- **Read back.** `curl -sS http://127.0.0.1:8123/lists` returns a list named `Maison Madira autumn list` with `budget` 1200000, `currency` `USD`, `target_margin` 3.2, and `item_count` 19. Money is in cents: the first item, `Muscadet Sèvre-et-Maine Sur Lie`, has `cost` 1800, `pour_price` 1600, and `bottle_price` 6200.
- **Proof.** Screenshot the summary and the table after the curator row is `COMPLETE`.
- **Import.** Stay on `/list`. Choose `[data-testid=list-import-file]` and the repo file `fixtures/sample_list.csv`. Choose `[data-testid=list-import-preview]`. On a fresh seed, `[data-testid=list-import-summary]` reads `1 matched · 0 new products · 4 new variants · 0 errors`. `[data-testid=list-import-preview-table]` shows `Muscadet Domaine de l'Ecu` as `Matched` (it is already in the cellar). `Chablis Premier Cru Vaillons` is `New variant` (`New variant of an existing product.`). A second import of the same file matches those rows instead. Choose `[data-testid=list-import-confirm]`. `[data-testid=list-import-entries]` then shows those names, including `Barolo` and `Kölsch`. `GET /lists` includes a list named `sample list` with `source_filename` `sample_list.csv` and `item_count` 5. The Chablis row is cost `3400`, pour `2200`, bottle `9600`. The Kölsch row is cost `240`, pour `900`, bottle `0`.
- **Read the import back.** `curl -sS http://127.0.0.1:8123/lists` includes a list whose `source_filename` is `sample_list.csv`. Money is in cents. `Chablis Premier Cru Vaillons` has `bottle_price` 9600, `pour_price` 2200, and `cost` 3400. `Kölsch` has `cost` 240. The file is under `MADIRA_STORAGE_DIR` (default `backend/data/storage`) after confirm, not after preview.
- **Catalog.** `curl -sS http://127.0.0.1:8123/products` returns `products`. After the confirm, one product's `name` is `Chablis Premier Cru Vaillons` and it has a `variants` array. Before the import, the seeded cellar is already there: a product named `Muscadet Domaine de l'Ecu`.
- **Notes.** Choose the button `Notes for Chablis Premier Cru Vaillons` (`[data-testid=list-entry-notes]`). `[data-testid=tasting-notes]` is visible. Choose `[data-testid=tasting-note-draft]`. `[data-testid=tasting-note-card]` shows status `Draft` and the hook starts with the bottle name (`Chablis Premier Cru Vaillons: Chardonnay, steel from Burgundy, ready to pour.`). `[data-testid=service-card]` is `Draft` and `[data-testid=service-card-glassware]` is `White wine glass`. Choose `[data-testid=tasting-note-edit]`, fill `[data-testid=tasting-note-hook-input]` with `Crisp and ready for oysters.`, and choose `[data-testid=tasting-note-save]`. The hook is that sentence and the status stays `Draft`. Choose `[data-testid=tasting-note-approve]`. The status is `Approved`. Choose `[data-testid=service-card-approve]`. The status is `Approved` and `[data-testid=service-card-temperature]` is `45-50°F`. The badge class uppercases those words, so `innerText` reads `DRAFT` and `APPROVED`. The DOM text stays `Draft` and `Approved`.
- **Read the note back.** Take the product `id` from `GET /products` and `curl -sS http://127.0.0.1:8123/products/<id>/notes`. The approved note's hook is `Crisp and ready for oysters.` `GET /products/<id>/service-cards` includes `glassware` `White wine glass` and `status` `approved`.
- **Publish.** In a context signed in as Lea (`POST /auth/demo-persona` `{"slug":"lea"}`), open `/list` and wait until `[data-testid=list-curate]` is enabled. Choose it. `[data-testid=list-editor]` opens. On a fresh seed the sections read `Wine 0` and `Beer 0` and the editor says `This list has no bottles yet.` `[data-testid=list-add-candidate]` lists cellar bottles (`Suntory Toki` among them). Choose one. A `[data-testid=list-item]` appears. Choose `[data-testid=list-diff-load]`. `[data-testid=list-diff-added]` is `Added 1`. Choose `[data-testid=list-submit]`. `[data-testid=list-pending]` is visible. Switch back to `owner`. On `/`, `[data-testid=tonight-approval]` contains `List publish`. On `/list`, select that list in `[data-testid=list-picker]` and choose `[data-testid=list-approve]`. `[data-testid=list-qr]` loads and `[data-testid=list-public-url]` starts with `/l/`. Open that href with no session. The page names `Maison Madira`, the list, and the bottle (`3 Fonteinen Oude Kriek`, `Glass $8.00 · Bottle $33.00` when that candidate was added). `[data-testid=mode-banner]` is absent. Source: `frontend/src/components/ListEditor.tsx`, `frontend/src/app/l/[token]/page.tsx`. Switch the persona back to `owner`.

## Gotchas

- The currency text uses a thousands separator (`$12,000`, `$5,198`). Assert the visible summary, not the raw prompt numbers alone. `GET /lists` stores money in cents, so `$12,000` is `budget` 1200000. A text read that follows CSS (`innerText`) uppercases the kicker and the category chip; the DOM text of the chip stays `wine 8`.
- Each curator run inserts another beverage list. Read the newest row, or the row whose budget and margin match the prompt. The imported list is the row whose `source_filename` is `sample_list.csv`.
- The seeded cellar already has `Chablis 1er Vaillons Droin`. That is a different product from `Chablis Premier Cru Vaillons` on the sample CSV.
- Notes are per product on the imported list. A row with no `product_id` has no Notes button.
