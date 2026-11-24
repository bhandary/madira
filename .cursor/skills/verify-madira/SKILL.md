---
name: verify-madira
description: Launch, doctor, drive, and clean up the Madira beverage-program app (Next.js floor at :3000, FastAPI at :8123) in demo mode. Use when a change needs proof of the Head Sommelier UI, a specialist surface, menu ingest, list import, the cellar ledger, phone counts, purchasing, receiving, records, sign-in, settings, or /health without an LLM key. Recipes are in features/.
---

# Verify Madira

Use this skill to prove the Head Sommelier stack from the user-facing floor and the public HTTP endpoints. Demo mode is the safe path: a deterministic fake model, no provider key, no email, and no Google round trip.

Read [features/README.md](features/README.md) before driving. Each feature file is the recipe. This file is only how to start, check, record, and stop.

## Launch

From the repo root, with no provider key and no Google or admin variables in the environment:

```bash
make install
mkdir -p /tmp/madira-verify
# Backend. Record the process id (the tmux pane pid after exec, or $! if backgrounded).
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GOOGLE_API_KEY -u MADIRA_API_KEY \
  -u GOOGLE_CLIENT_ID -u GOOGLE_CLIENT_SECRET -u MADIRA_AUTH_SECRET \
  -u MADIRA_PUBLIC_URL -u MADIRA_OWNER_EMAIL -u MADIRA_DEMO_MODE \
  PYTHONPATH=backend backend/.venv/bin/python -m madira.main
# Frontend, in a second session. Playwright and the doctor use 127.0.0.1.
cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3000
```

`make dev` starts the same two programs. A verification run starts them separately so cleanup can kill the recorded pids. Write those pids to `/tmp/madira-verify/backend.pid` and `/tmp/madira-verify/frontend.pid`. The frontend pid is `npm`; the listener on the port is its `next-server` child.

`next dev` can exit right after `Ready` with `This command stopped to show the upgrade recommendation` and leave nothing on the port. Start the same frontend command once more; the next start prints `This command is continuing after the upgrade reminder` and stays up. Do not run the suggested `next upgrade` during a verification run. It changes product code.

If `make` is not installed, run the recipe lines from the `Makefile` targets (`install`, `doctor`, `clean`) directly from the repo root.

Ready means usable:

- Backend log contains `Application startup complete` and `Uvicorn running on http://0.0.0.0:8123`. Startup seeds `backend/data/madira.db` before the process accepts connections.
- `curl -sS http://127.0.0.1:8123/health` returns `"status": "ok"`, `"demo_mode": true`, and `"label": "DEMO MODE — deterministic fixtures, no API key"`.
- Frontend log contains `Ready` and `Local: http://127.0.0.1:3000`.
- `http://127.0.0.1:3000/` returns 200, and `[data-testid=mode-banner]` has left the word `connecting`.

`make install` needs `python3 -m venv` (Debian/Ubuntu: `python3.12-venv`). Do not set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `MADIRA_API_KEY`.

Default ports are backend `8123` and frontend `3000`, and both processes share `backend/data/madira.db`. If either port is taken by something this run did not start, move the pair instead of stopping it:

- Backend: add `MADIRA_PORT=<port>`, `MADIRA_FRONTEND_ORIGIN=http://127.0.0.1:<frontend port>`, and `MADIRA_DATA_DIR=<empty dir>` so it gets its own sqlite file.
- Frontend: `MADIRA_BACKEND_URL=http://127.0.0.1:<backend port> npm run dev -- --hostname 127.0.0.1 --port <frontend port>`. This feeds both the `/madira-api` rewrite and the `/api/copilotkit` runtime.
- Next allows one dev server per checkout. A second `next dev` in the same `frontend/` prints `You can access the existing server at …` and exits. Use another clone for a second pair.
- Replace `8123` and `3000` in the doctor and the recipes with the ports you chose. `make doctor` only checks the default ports.

## Doctor

Run this before the first drive, and again after any drive that fails or returns something unexpected.

```bash
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GOOGLE_API_KEY -u MADIRA_API_KEY -u MADIRA_DEMO_MODE make doctor
curl -sS http://127.0.0.1:8123/health
curl -sS http://127.0.0.1:8123/status
```

`make doctor` prints `status_payload()` (no request), then the live `/health` body, then `frontend ok` on the same line as the closing brace. The first block is computed in the shell that runs `make doctor`, not in the backend. Run it with the same variables unset as the backend launch. With `OPENAI_API_KEY` set in that shell it printed `"demo_mode": false` and `LIVE — openai:gpt-4.1-mini` while the backend's `/health` said demo. Worth driving when all of these hold:

- The listeners on `8123` and `3000` are the recorded pids or their children.
- `/health` and `/status` agree: `demo_mode` true, label `DEMO MODE — deterministic fixtures, no API key`, `llm_model` `madira-demo-fixtures`, `database` `sqlite`.
- `/status` `specialists` is `menu-analyst`, `pairing-sommelier`, `list-curator`, `inventory-purchasing`, `staff-trainer`, `supplier-scheduler`, and `compliance-auditor`, and `wiring.has_task_tool` is true.
- The floor banner reads `DEMO MODE` and `deterministic fixtures, no API key`, not `connecting`.

`make test` is the suite check (Deep Agents wiring). It is not a substitute for a live drive. Run it from the repo root when you need the suite result. Frontend checks, from `frontend/`: `npm run lint` and `npx tsc --noEmit`.

## Drive

Use Playwright against `http://127.0.0.1:3000` and curl against `http://127.0.0.1:8123`. The browser reaches the API through the Next rewrite `/madira-api/*`.

Wait until a workbench `Run specialists` button (`[data-testid=<page>-workbench-submit]`) is enabled before clicking it. The server renders it `disabled`, and it stays disabled until the page has connected to the agent thread.

The floor banner is `DEMO MODE` plus `connecting` until `GET /status` returns. Wait until `connecting` is gone.

On `/`, the floor's only heading is the level-1 `Ask the Head Sommelier`. `next dev` also mounts `Upgrade Next.js to a safe version.` as a heading inside the Next.js overlay shadow root (`#nextjs__container_errors_desc`). Playwright locators pierce that root, so a count of every heading on the page is 2. That advisory is not part of the floor.

Conversations persist. Each page keeps its thread id in `localStorage` (`madira-thread:floor`, `madira-thread:<page>-workbench`), and the backend stores the thread in the sqlite checkpoint tables. Reloading a page in the same browser context restores the earlier messages, surfaces, and delegation rows. For a clean page, open it in a new browser context.

Follow [features/README.md](features/README.md), then the feature file. Drive the real controls. Read back side effects with the GET listed in that file.

## Evidence

Set `MADIRA_EVIDENCE_DIR` or use `/tmp/madira-verify-evidence`. Create it before the drive. Do not write proof under `backend/data/`, `frontend/.next/`, `test-results/`, or `playwright-report/`. `make clean` deletes those.

For each feature, keep the action and the resulting state: a full-page screenshot, the visible testid text, and the read-back response (inventory row, menu list, list row, quiz attempts, tasting `.ics`). A screenshot of the form before Run specialists is not proof.

## Cleanup

Kill the recorded pids and their children. Do not `pkill` by process name.

```bash
kill_tree() {
  local pid="$1" child
  for child in $(ps -o pid= --ppid "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}
kill_tree "$(cat /tmp/madira-verify/backend.pid)"
kill_tree "$(cat /tmp/madira-verify/frontend.pid)"
```

After the listeners are gone, `make clean` removes the sqlite file this run seeded (data and checkpoints), `frontend/.next`, `test-results`, and `playwright-report`. It leaves `backend/data/madira.db-wal`, `backend/data/madira.db-shm`, and `backend/data/.madira_secret`; remove the `-wal` and `-shm` files too. Leave `fixtures/` and `MADIRA_EVIDENCE_DIR` in place. Confirm the evidence directory still contains the screenshots after cleanup.

## Maintain

When the floor changes, run `/maintain-verification-skill` so this map stays tied to a live drive.
