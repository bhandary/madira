---
name: verify-madira
description: Launch, doctor, drive, evidence, and cleanup for the Madira beverage-program app.
---

# Verify Madira

Use this skill to prove the Head Sommelier stack works without secrets (demo mode).

## Launch

From the repo root:

```bash
make install
make dev
```

- Backend: `http://127.0.0.1:8123/health` — `demo_mode: true` when no API key.
- Frontend: `http://127.0.0.1:3000`
- Do not set `OPENAI_API_KEY` unless you intend to leave demo mode.

If ports are busy, stop leftover uvicorn/next processes. Data lives in `backend/data/madira.db` (safe to delete to reseed).

## Doctor

```bash
make doctor
make test
curl -s http://127.0.0.1:8123/status | python3 -m json.tool
```

Confirm:

- `demo_mode` is true and the banner says DEMO MODE
- `specialists` lists `menu-analyst`, `pairing-sommelier`, `list-curator`, `inventory-purchasing`, `staff-trainer`, `supplier-scheduler`
- pytest: orchestrator exposes those subagents and `invoke_head_sommelier` records `task` delegations plus A2UI `createSurface` ops

## Drive

Prefer Playwright (headless is fine in CI; headed for walkthrough video):

```bash
cd frontend && npx playwright test
```

Manual / computer-use journey (same order as `e2e/journey.spec.ts`):

1. **Menu & pairings** (`/menu`) — paste or upload `fixtures/sample_menu.txt` (PDF/image also accepted). Run specialists. Wait for `[data-testid=pairing-grid]` A2UI cards and `[data-testid=delegation-panel]` showing `menu-analyst` then `pairing-sommelier`.
2. **List curation** (`/list`) — budget `12000`, margin `3.2`. Wait for `[data-testid=beverage-list-table]` and `[data-testid=list-summary]` with cost/margin.
3. **Inventory** (`/inventory`) — set `W-MUS-01` on-hand to `1`, Adjust stock, Run specialists. Wait for `[data-testid=purchase-order-table]` draft (must say draft / not sent).
4. **Training** (`/training`) — Quiz mode (answers `1,2,2,1`). Wait for `[data-testid=quiz-card]` and `[data-testid=quiz-score]`.
5. **Suppliers** (`/suppliers`) — Run the default tasting prompt. Wait for `[data-testid=tasting-calendar]` and `[data-testid=ics-block]` containing `BEGIN:VCALENDAR`. Nothing is emailed.

## Evidence

Save under the run artifacts directory (and `artifacts/` in-repo if needed):

- Screenshots of each of the five states above
- One video of the full journey (`madira_full_journey`)
- pytest output for subagent wiring

A screenshot of a static page is not enough — pairing cards, list table, PO draft, quiz score, and .ics must be visible after an agent run.

## Cleanup

```bash
pkill -f "python -m madira.main" || true
pkill -f "next dev" || true
make clean
```

Do not delete `fixtures/`. Do not force-push. Do not push to `main`.
