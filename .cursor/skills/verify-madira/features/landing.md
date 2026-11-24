# Floor chat

The floor is a Head Sommelier chat with four section cards beside it. In demo mode the banner says DEMO MODE, the sidebar lists the ten sections, and a message about the supplier calendar returns a reply plus an empty tasting calendar when no tasting has been stored yet. The conversation is kept: a reload in the same browser shows it again.

## Sub-features

- `floor-banner` shows DEMO MODE once status has loaded.
- `floor-nav` lists the ten sections and a Sign in link.
- `floor-chat` sends a message and renders the assistant reply in the chat.
- `floor-cards` links to Menu & pairings, Cellar, List, and Team from the home page.
- `floor-sections` opens More on a narrow viewport.

## How to get to it (user POV)

- Open `http://127.0.0.1:3000/`.
- Choose `Floor` in the sidebar. The link is the first item in `[id=app-nav]`.
- On a 390px-wide viewport, choose the `Floor` tab. `More` opens `[data-testid=mobile-menu]` for purchasing, the phone count, suppliers, records, settings, and sign-in.

## Driving it with Playwright and curl

Preconditions:

- `/health` reports `demo_mode` true.
- No tasting has been stored yet if the empty calendar is the assertion. A later supplier run inserts one.

- **Banner.** Open `/`. Wait until `[data-testid=mode-banner]` does not contain `connecting`. The banner text is `DEMO MODE` and `deterministic fixtures, no API key`. The level-1 heading named `Ask the Head Sommelier` is visible. It is the only heading in the floor document.
- **Nav.** Read the links in `#app-nav`. They are `Floor`, `Menu & pairings`, `List curation`, `Inventory`, `Purchasing`, `Phone count`, `Staff training`, `Supplier tastings`, `Records`, `Settings`. The sidebar `[data-testid=sign-in-link]` reads `Sign in`.
- **Cards.** The `a.bento` links are `Menu & pairings` (`/menu`), `Cellar` (`/inventory`), `List` (`/list`), and `Team` (`/training`), each with a one-line description and `Open`. Choosing `Cellar` lands on `/inventory`.
- **Send.** In `.sommelier-chat` (`[data-testid=copilot-chat]` on the floor wrapper), fill the placeholder `Type a message...` with `Show the supplier tasting calendar.` and choose the button `Send message`. The chat text contains `Head Sommelier` and `nothing was emailed or purchased`. `[data-testid=copilot-chat-error]` is absent. `[data-testid=tasting-calendar]` is visible and reads `No tastings held yet.`
- **Kept.** Reload `/` in the same browser context. The prompt, the calendar, and the reply are back without sending again.
- **Narrow nav.** Set the viewport to 390×844 and open `/inventory`. `Supplier tastings`, `Purchasing`, `Phone count`, and `Records` are not in the tab bar. Choose `More`. `[data-testid=mobile-menu]` shows `Purchasing`, `Phone count`, `Supplier tastings`, `Records`, and `Settings`.
- **Proof.** Screenshot the banner and cards before send, the chat after the calendar line appears, and the open `More` menu.

## Gotchas

- The banner reads `DEMO MODE connecting` until `GET /status` returns. Do not assert the model label during that gap.
- `next dev` adds a second heading, `Upgrade Next.js to a safe version.`, in the Next.js overlay shadow root (`#nextjs__container_errors_desc`). Playwright counts it. The floor still has one heading.
- Do not wait for an empty-chat heading such as `How can I help you today?`. The page has none.
- Because the conversation is kept, a second drive in the same browser context starts with the earlier messages. Use a new context for the empty state.
- The chat calendar lists stored tastings. After a supplier run it is no longer empty.
- The send control is the accessible name `Send message`, not the arrow icon alone.
- CopilotKit stamps `data-testid=copilot-chat` on its own root as well as on `.sommelier-chat`. A strict Playwright locator for that testid matches both. Scope the fill and the click to `.sommelier-chat`.
