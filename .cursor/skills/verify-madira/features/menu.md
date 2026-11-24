# Menu and pairings

Menu & pairings takes a pasted or uploaded menu and shows a parsed dish list plus pairing cards for wine, beer, spirit, and sake. The same page can read a photo or a text file, hold the dishes for review, and then pin, swap, or reject pairings drawn from bottles on the list. The rail names Menu Analyst and Pairing Sommelier.

## Sub-features

- `menu-sample` loads the Maison Madira tasting menu into the prompt.
- `menu-upload` records the chosen file name.
- `menu-run` delegates to `menu-analyst` and `pairing-sommelier` and renders both surfaces.
- `menu-stored` keeps the parsed menu for a later GET.
- `menu-ingest` reads `fixtures/sample_menu.png`, shows a draft dish list, and keeps an edited sauce after confirm.
- `menu-pair` builds stock-grounded slots for a confirmed menu and keeps a pin, a swap, and a rejection.

## How to get to it (user POV)

- Choose `Menu & pairings` in the sidebar, or open `http://127.0.0.1:3000/menu`.
- On a narrow viewport, choose the `Menu` tab.
- Below the workbench, `Read a menu` is `[data-testid=menu-ingest]`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- `fixtures/sample_menu.txt` is the workbench upload. It is the five-dish Maison Madira autumn menu, starting with Dungeness crab.
- `fixtures/sample_menu.png` is the ingest photo.
- For `menu-pair`, import [the sample list](./list.md) first so the swap list has more than the seeded bottles. Pairing still runs against the seeded catalog if you skip the import; a slot with no listed bottle reads `No listed bottle`.

- **Wait for the sample.** Open `/menu`. The heading is `Menu & pairings`. Wait until `[data-testid=menu-workbench-prompt]` contains `Dungeness`. The prompt starts `Parse this menu (PDF/image/text)`.
- **Upload.** Set `[data-testid=menu-file]` to `fixtures/sample_menu.txt`. `[data-testid=menu-filename]` reads `sample_menu.txt`. The prompt still contains `Dungeness crab`.
- **Run.** Choose `[data-testid=menu-workbench-submit]` once it is enabled. Wait until `[data-testid=delegate-menu-analyst]` and `[data-testid=delegate-pairing-sommelier]` are visible. Both show `COMPLETE`.
- **Surfaces.** The assistant message says the head delegated to `menu-analyst, pairing-sommelier`. `[data-testid=dish-list]` lists five dishes, starting with `Dungeness crab, yuzu, avocado, cucumber` and including the mousse, risotto, ribeye, and chocolate. There is no `Parsed ·` heading. `[data-testid=pairing-grid]` is the same stock-grounded grid as the ingest page: one `[data-testid=pairing-card]` per dish, each with `pairing-slot-best_by_the_glass`, `pairing-slot-best_bottle`, `pairing-slot-value`, and `pairing-slot-adventurous`. There is no `pairing-wine`, `pairing-beer`, `pairing-spirit`, or `pairing-sake`. With the sample list imported, the first card's glass slot names `Sancerre`, the bottle slot names `Valdespino Inocente`, the value slot names `Kölsch`, and the adventurous slot names `Banyuls`. A slot with no listed bottle reads `No listed bottle`. The pin, swap, and reject controls are on this grid too. `[data-testid=todo-list]` reads `[in_progress] Delegate to menu-analyst [pending] Delegate to pairing-sommelier`.
- **Read back.** `curl -sS http://127.0.0.1:8123/menus` includes a menu named `Maison Madira — Autumn Tasting`, cuisine `California-French`, price tier `$$$`, `dish_count` 5, `status` `confirmed`, and a UUID `id`. The workbench tool saves the parse as confirmed (`parse_menu` passes `confirm=True`). The review card under `Read a menu` is a separate draft until you confirm it.
- **Ingest.** On `/menu` at 390×844, set `[data-testid=menu-camera]` to `fixtures/sample_menu.png`. Its `accept` is `image/*;capture`. Choose `[data-testid=menu-ingest-submit]`. `[data-testid=dish-review]` is visible and `[data-testid=dish-review-status]` text is `Draft` (the badge's `innerText` is `DRAFT`). The first `[data-testid=dish-name]` contains `Dungeness crab`. `[data-testid=dish-field-sauce]` is `yuzu`. The photo review shows `[data-testid=dish-flag]` `LOW CONFIDENCE`. Fill the sauce with `yuzu kosho` and choose `[data-testid=dish-save]`. `[data-testid=dish-value-sauce]` contains `yuzu kosho`. Choose `[data-testid=dish-confirm]`. The status text is `Confirmed` and the sauce value is still `yuzu kosho`.
- **Pair.** In a context that already confirmed a text ingest of `fixtures/sample_menu.txt` (`[data-testid=menu-ingest-file]`, then submit, then confirm), choose `[data-testid=menu-pair]`. Inside `[data-testid=menu-ingest]`, the first `[data-testid=pairing-card]` has the four slots above. A stocked slot's `[data-testid=pairing-name]` is a bottle name, not `No listed bottle`. Pin the glass slot (`[data-testid=pairing-pin]`) and wait until its `[data-testid=pairing-status]` text is `Pinned`. A click that is not followed by that wait can be lost while the page is still settling; the status is the proof. On the bottle slot, choose the second option in `[data-testid=pairing-swap-select]`, choose `[data-testid=pairing-swap]`, and the status text becomes `Swapped` with a different name. Reject the value slot; its status text becomes `Rejected` and the name stays. Reload `/menu`. The same statuses and names are still on that card. The badge class uppercases the visible `innerText` (`PINNED`, `SWAPPED`, `REJECTED`). The DOM text stays `Pinned`, `Swapped`, `Rejected`.
- **Read the pairings back.** `curl -sS http://127.0.0.1:8123/menus/<id>/pairings` returns `dishes`. The first dish's pairings include `status` `pinned`, `swapped`, and `rejected` on those slots.
- **Proof.** Screenshot the workbench dish list and pairing cards, the confirmed review, and the pinned slot.

## Gotchas

- The todo list keeps the head's last `write_todos` call, so it still shows `in_progress` and `pending` after both specialists are `COMPLETE`. Do not read it as run status.
- Each workbench run inserts another menu. `GET /menus` lists the newest first.
- A text upload on the workbench keeps the dish text in the prompt. The ingest form is a separate control (`menu-ingest-file`, `menu-camera`). Do not set `menu-file` and expect the review card.
- `GET /fixtures/sample-menu` returns the same autumn menu text (`text` is 347 characters) and is what the page loads into the prompt before an upload. It is demo-only: with a key saved it returned 501.
- The workbench and the ingest form render the same `PairingGrid`. Pin, swap, and reject work on both. `pairing-wine` and the other category test ids are not in the page.
- `menu-pair` stays disabled until a review is on the page. Confirm the dishes first.
