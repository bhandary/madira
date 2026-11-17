# Madira verification map

This directory is the maintained source for verifying Madira's user-facing floor and the public HTTP endpoints. Read this index first, then drive one feature file at a time.

## Baseline preconditions

- Launch from the repo root with the commands in [../SKILL.md](../SKILL.md). Backend `http://127.0.0.1:8123`, frontend `http://127.0.0.1:3000`.
- Demo mode: no `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `MADIRA_API_KEY`. Do not set `MADIRA_DEMO_MODE`.
- Google sign-in unset: no `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MADIRA_AUTH_SECRET`, or `MADIRA_PUBLIC_URL`.
- Settings opens as the demo Owner. No shared admin password.
- Empty data dir is fine. Startup creates `backend/data/madira.db` and seeds the cellar, suppliers, lessons, and quiz.
- `make doctor` shows `demo_mode` true and `frontend ok`.
- Never drive an instance this run did not start. Ports `8123` and `3000` and the sqlite file are shared. If they are taken, move this run's pair to other ports as [../SKILL.md](../SKILL.md) describes.

## Driving conventions

- Start every recipe from a healthy demo instance. Doctor again after a failed drive.
- Prefer `data-testid` and the accessible names in the feature file. The sidebar nav labels are `Floor`, `Menu & pairings`, `List curation`, `Inventory`, `Staff training`, `Supplier tastings`, and `Settings`.
- At 390px width the sidebar is hidden. A bottom tab bar shows `Floor`, `Menu`, `Cellar`, `List`, and `Team`. `More` opens `[data-testid=mobile-menu]` with `Supplier tastings`, `Settings`, and sign-in. Observed on `/inventory`: `Supplier tastings` was absent until `More` was clicked.
- Wait until the workbench submit button is enabled. It is rendered `disabled` and stays that way until the page has connected to its agent thread.
- Wait until `[data-testid=mode-banner]` no longer contains `connecting`.
- A finished specialist run shows `Head Sommelier here. I delegated to … and they posted surfaces in the well. Review the cards and tables — nothing was emailed or purchased.` in the last `[data-testid=copilot-assistant-message]`. `[data-testid=agent-reply]` is the whole conversation: your prompt (`[data-testid=copilot-user-message]`), the surfaces, and that sentence. The delegation rail shows the specialist name and the visible status `COMPLETE`. While the specialist runs, `[data-testid=agent-working]` reads `Working…`.
- `Run specialists` sends `POST /api/copilotkit/agent/head_sommelier/run`. Assert the surface, then read it back with the GET in the feature file.
- A reload in the same browser context restores the page's earlier conversation and surfaces. Use a new browser context when a recipe needs a page with nothing on it.
- Restore `W-MUS-01` on-hand if a recipe changes it. Drive [Settings](./settings.md) last: its key save locks every other feature until the stored key is deleted and the backend restarted. Leave proof files in `MADIRA_EVIDENCE_DIR` (default `/tmp/madira-verify-evidence`).

## Proof and skip reporting

- Capture the click or request and the resulting state, not only the final screen.
- UI proof is the testid text plus a full-page screenshot that still shows the `DEMO MODE` banner.
- HTTP proof is the status, content type, and body.
- Mutation proof is a second GET of the stored row, attempt, menu, list, or `.ics`.
- Report an unreachable path with the URL tried and the missing precondition. The Google account round trip is not part of this baseline. Settings opens as the demo Owner, so a key save is reachable when `MADIRA_LLM_VALIDATOR=accept`.

## Feature entry contract

Each feature file starts with an H1 and one paragraph of user-visible behavior, then these four H2 sections in order:

1. `Sub-features`
2. `How to get to it (user POV)`
3. `Driving it with Playwright and curl`
4. `Gotchas`

## Features

- [Floor chat](./landing.md) — Head Sommelier chat on `/`, demo banner, sidebar, section cards, and the narrow `More` menu.
- [Menu and pairings](./menu.md) — paste or upload a menu, then dish list and pairing cards.
- [List curation](./list.md) — budget and target multiple, then the list table and summary.
- [Inventory](./inventory.md) — adjust a SKU, then draft purchase orders that stay unsent.
- [Staff training](./training.md) — quiz, briefing, and roleplay buttons.
- [Supplier tastings](./suppliers.md) — draft tasting, calendar, and `.ics` that is not sent.
- [Sign in](./login.md) — Google button absent, and the not-configured notice.
- [Settings](./settings.md) — demo Owner key form, saving a key, then the locked page and refused endpoints.
- [Health and status](./health.md) — `/health`, `/status`, and the Next rewrite.
