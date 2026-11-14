---
name: verify-madira
description: Launch, doctor, drive, and clean up the Madira beverage-program app (Next.js floor at :3000, FastAPI at :8123) in demo mode. Use when a change needs proof of the Head Sommelier UI, a specialist surface, sign-in, settings, or /health without an LLM key. Recipes are in features/.
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
  -u MADIRA_PUBLIC_URL -u MADIRA_ADMIN_PASSWORD -u MADIRA_DEMO_MODE \
  PYTHONPATH=backend backend/.venv/bin/python -m madira.main
# Frontend, in a second session. Playwright and the doctor use 127.0.0.1.
cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3000
```

`make dev` starts the same two programs. A verification run starts them separately so cleanup can kill the recorded pids. Write those pids to `/tmp/madira-verify/backend.pid` and `/tmp/madira-verify/frontend.pid`.

Ready means usable:

- Backend log contains `Application startup complete` and `Uvicorn running on http://0.0.0.0:8123`. Startup seeds `backend/data/madira.db` before the process accepts connections.
- `curl -sS http://127.0.0.1:8123/health` returns `"status": "ok"`, `"demo_mode": true`, and `"label": "DEMO MODE — deterministic fixtures, no API key"`.
- Frontend log contains `Ready` and `Local: http://127.0.0.1:3000`.
- `http://127.0.0.1:3000/` returns 200, and `[data-testid=mode-banner]` has left the word `connecting`.

`make install` needs `python3 -m venv` (Debian/Ubuntu: `python3.12-venv`). Do not set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `MADIRA_API_KEY`.

One instance only. Backend port `8123` and frontend port `3000` are fixed, and both processes share `backend/data/madira.db`. Do not start a second pair.

## Doctor

Run this before the first drive, and again after any drive that fails or returns something unexpected.

```bash
make doctor
curl -sS http://127.0.0.1:8123/health
curl -sS http://127.0.0.1:8123/status
```

`make doctor` prints `status_payload()` (no request), then the live `/health` body, then `frontend ok` on the same line as the closing brace. Worth driving when all of these hold:

- The recorded pids are still the listeners on `8123` and `3000`.
- `/health` and `/status` agree: `demo_mode` true, label `DEMO MODE — deterministic fixtures, no API key`, `llm_model` `madira-demo-fixtures`, `database` `sqlite`.
- `/status` `specialists` is `menu-analyst`, `pairing-sommelier`, `list-curator`, `inventory-purchasing`, `staff-trainer`, `supplier-scheduler`, and `wiring.has_task_tool` is true.
- The floor banner reads `DEMO MODE` and `deterministic fixtures, no API key`, not `connecting`.

`make test` is the suite check (Deep Agents wiring). It is not a substitute for a live drive. Run it from the repo root when you need the suite result. Frontend checks, from `frontend/`: `npm run lint` and `npx tsc --noEmit`.

## Drive

Use Playwright against `http://127.0.0.1:3000` and curl against `http://127.0.0.1:8123`. The browser reaches the API through the Next rewrite `/madira-api/*`.

Wait until a submit control has a React property (`__react` on the DOM node) before clicking it. A click before hydration submits the form as GET and lands on the same path with a trailing `?`, and the specialist does not run.

The floor banner is `DEMO MODE` plus `connecting` until `GET /status` returns. Wait until `connecting` is gone.

On `/`, two level-1 headings exist: `Ask the Head Sommelier` and the empty-chat heading `How can I help you today?`. Target the page heading by name.

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

After the listeners are gone, `make clean` removes the sqlite file this run seeded, `frontend/.next`, `test-results`, and `playwright-report`. Leave `fixtures/` and `MADIRA_EVIDENCE_DIR` in place. Confirm the evidence directory still contains the screenshots after cleanup.

## Maintain

When the floor changes, run `/maintain-verification-skill` so this map stays tied to a live drive.
