# Menu and pairings

Menu & pairings takes a pasted or uploaded menu and shows a parsed dish list plus pairing cards for wine, beer, spirit, and sake. The rail names Menu Analyst and Pairing Sommelier.

## Sub-features

- `menu-sample` loads the Maison Madira tasting menu into the prompt.
- `menu-upload` records the chosen file name.
- `menu-run` delegates to `menu-analyst` and `pairing-sommelier` and renders both surfaces.
- `menu-stored` keeps the parsed menu for a later GET.

## How to get to it (user POV)

- Choose `Menu & pairings` in the sidebar, or open `http://127.0.0.1:3000/menu`.
- On a narrow viewport, choose the `Menu` tab.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- `fixtures/sample_menu.txt` is the upload. It is the five-dish Maison Madira autumn menu, starting with Dungeness crab.

- **Wait for the sample.** Open `/menu`. The heading is `Menu & pairings`. Wait until `[data-testid=menu-workbench-prompt]` contains `Dungeness`. The prompt starts `Parse this menu (PDF/image/text)`.
- **Upload.** Set `[data-testid=menu-file]` to `fixtures/sample_menu.txt`. `[data-testid=menu-filename]` reads `sample_menu.txt`. The prompt still contains `Dungeness crab`.
- **Run.** Choose `[data-testid=menu-workbench-submit]` once it is enabled. Wait until `[data-testid=delegate-menu-analyst]` and `[data-testid=delegate-pairing-sommelier]` are visible. Both show `COMPLETE`.
- **Surfaces.** The assistant message says the head delegated to `menu-analyst, pairing-sommelier`. The well shows `Parsed · Maison Madira — Autumn Tasting` with five dishes (crab, mousse, risotto, ribeye, chocolate). `[data-testid=pairing-grid]` is visible. The first `[data-testid=pairing-card]` names `Dungeness crab, yuzu, avocado, cucumber`. The first `[data-testid=pairing-wine]` names `Muscadet Sèvre-et-Maine Sur Lie`. Beer, spirit, and sake cards are on the same grid (`[data-testid=pairing-beer]`, `pairing-spirit`, `pairing-sake`, five of each). `[data-testid=todo-list]` reads `[in_progress] Delegate to menu-analyst [pending] Delegate to pairing-sommelier`.
- **Read back.** `curl -sS http://127.0.0.1:8123/menus` includes a menu named `Maison Madira — Autumn Tasting`, cuisine `California-French`, price tier `$$$`, `dish_count` 5, and a UUID `id`.
- **Proof.** Screenshot the dish list and the pairing cards together.

## Gotchas

- The todo list keeps the head's last `write_todos` call, so it still shows `in_progress` and `pending` after both specialists are `COMPLETE`. Do not read it as run status.
- Each run inserts another menu. `GET /menus` lists the newest first.
- A text upload keeps the dish text in the prompt. This drive did not upload a PDF or an image.
- `GET /fixtures/sample-menu` returns the same autumn menu text (`text` is 347 characters) and is what the page loads into the prompt before an upload. It is demo-only: with a key saved it returned 501.
