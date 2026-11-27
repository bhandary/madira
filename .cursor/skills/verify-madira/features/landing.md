# Tonight

Tonight is the service board on `/`. It shows the published briefing, low stock, storage, sensors, reminders, deliveries, POS gaps, certificates, and approvals, and the Head Sommelier chat sits under that board. The level-1 heading is `Tonight`.

## Sub-features

- `tonight-board` loads `GET /tonight` for the Owner and shows the section headings.
- `tonight-briefing` walks the published cards and acknowledges the last one.
- `tonight-chat` still sends a floor message and gets a demo delegation reply.
- `tonight-nav` is the desktop sidebar and the phone `More` sheet.

## How to get to it (user POV)

- Open `http://127.0.0.1:3000/`.
- The desktop sidebar's first link is `Tonight`.
- On a phone the first tab is `Tonight`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. The active persona is the demo Owner (`Demo Owner`).
- A published briefing exists. `POST http://127.0.0.1:8123/tonight/briefing/rebuild` and then `POST /tonight/briefing/publish` are both 200. Source: `frontend/src/app/page.tsx`, `frontend/src/components/BriefingCards.tsx`.

- **Board.** Open `/`. The level-1 heading is `Tonight`. The lead is `The floor, before service.` `[data-testid=lookup-link]` reads `Lookup`. With a published briefing, `[data-testid=briefing-stack]` is visible.
- **Acknowledge.** Choose `[data-testid=briefing-next]` until `[data-testid=briefing-ack]` is visible, then choose it. `[data-testid=briefing-acked]` reads `Acknowledged in 1s.`
- **Empty sections.** On a fresh seed before any sensor or POS run, the Sensors section says `No sensors yet.` and the POS section says `No POS gaps.` The certificates section says `No certificates are due.`
- **Chat.** In `.sommelier-chat`, fill `Type a message...` with `What is open by the glass?` and choose `Send message`. The last `[data-testid=copilot-assistant-message]` names a specialist and says nothing was emailed or purchased. Scope the chat to `.sommelier-chat`. CopilotKit also stamps `data-testid=copilot-chat` on an inner node.
- **Phone nav.** At 390×844 on `/inventory`, `Suppliers` is not a visible link until `More` is opened. `[data-testid=mobile-menu]` then contains `Suppliers`, `Tastings`, `Sourcing`, `POS`, `Sensors`, `Audit`, `Usage`, `Records`, and `Settings`.
- **Read back.** `curl -sS http://127.0.0.1:8123/tonight` includes `role`, `low_stock`, and `briefing`.
- **Proof.** Screenshot the briefing card and the assistant reply.

## Gotchas

- `next dev` may add `Upgrade Next.js to a safe version.` as a heading inside the Next.js overlay. The floor's own level-1 heading is `Tonight`.
- Staff (`POST /auth/demo-persona` body `{"slug":"ana"}`) sees three phone tabs, `Tonight`, `Lookup`, and `Lessons`, and no `More` button. A Staff visit to `/menu` is replaced with `/`. Switch back with `{"slug":"owner"}` before an Owner recipe.
- The offline board (`?day=` or the browser `offline` event) hides the live sections and says the rest of the board needs the network. The service worker registers only when the `madira_sw` cookie is `1` (`frontend/e2e/pwa-offline.spec.ts`).
- The chat thread is stored in `localStorage` (`madira-thread:floor`). A new browser context is a clean chat.
