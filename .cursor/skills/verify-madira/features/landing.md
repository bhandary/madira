# Floor chat

The floor is a Head Sommelier chat. In demo mode the banner says DEMO MODE, the sidebar lists the sections, and a message about the supplier calendar returns a reply plus an empty tasting calendar when no tasting has been stored yet.

## Sub-features

- `floor-banner` shows DEMO MODE once status has loaded.
- `floor-nav` lists the seven sections and a Sign in link.
- `floor-chat` sends a message and renders the assistant reply in the chat.
- `floor-sections` opens the section list on a narrow viewport.

## How to get to it (user POV)

- Open `http://127.0.0.1:3000/`.
- Choose `Floor` in the sidebar. The link is the first item in `[id=app-nav]`.
- On a 390px-wide viewport, choose `Sections`, then `Floor` inside `[data-testid=mobile-menu]`.

## Driving it with Playwright and curl

Preconditions:

- `/health` reports `demo_mode` true.
- No tasting has been stored yet if the empty calendar is the assertion. A later supplier run inserts one.

- **Banner.** Open `/`. Wait until `[data-testid=mode-banner]` does not contain `connecting`. The banner text is `DEMO MODE` and `deterministic fixtures, no API key`. The level-1 heading named `Ask the Head Sommelier` is visible. The chat also has a heading `How can I help you today?`.
- **Nav.** Read the links in `#app-nav`. They are `Floor`, `Menu & pairings`, `List curation`, `Inventory`, `Staff training`, `Supplier tastings`, `Settings`. The sidebar `[data-testid=sign-in-link]` reads `Sign in`.
- **Send.** In `[data-testid=copilot-chat]`, fill the placeholder `Type a message...` with `Show the supplier tasting calendar.` and choose the button `Send message`. The chat text contains `Head Sommelier` and `nothing was emailed or purchased`. `[data-testid=copilot-chat-error]` is absent. `[data-testid=tasting-calendar]` is visible and reads `No tastings held yet.`
- **Narrow nav.** Set the viewport to 390×844 and open `/inventory`. `Supplier tastings` is hidden. Choose `Sections`. `[data-testid=mobile-menu]` shows `Supplier tastings`.
- **Proof.** Screenshot the banner before send, the chat after the calendar line appears, and the open `Sections` menu.

## Gotchas

- The banner reads `DEMO MODE connecting` until `GET /status` returns. Do not assert the model label during that gap.
- `getByRole('heading', { level: 1 })` matches two headings. Name `Ask the Head Sommelier`.
- The chat calendar lists stored tastings. After a supplier run it is no longer empty.
- The send control is the accessible name `Send message`, not the arrow icon alone.
