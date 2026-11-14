# Health and status

Health and status say whether this process is the demo stack. The floor banner reads the same label. The Next app proxies the backend under `/madira-api`.

## Sub-features

- `health-direct` answers `GET /health` on port 8123.
- `health-rewrite` answers the same payload through the frontend.
- `status-specialists` lists the six specialists and the task-tool wiring.
- `status-banner` matches the banner on the floor.

## How to get to it (user POV)

- There is no nav item. The banner on every page shows the label from status.
- A terminal on the machine can request `http://127.0.0.1:8123/health` and `http://127.0.0.1:8123/status`.
- The browser origin equivalent is `http://127.0.0.1:3000/madira-api/health`.

## Driving it with Playwright and curl

Preconditions:

- The recorded backend pid is the listener on port 8123, and the recorded frontend pid is the listener on port 3000.
- No provider key is set.

- **Direct health.** `curl -sS http://127.0.0.1:8123/health` is 200 and JSON: `status` `ok`, `app` `madira`, `demo_mode` true, `llm_provider` `openai`, `llm_model` `madira-demo-fixtures`, `llm_source` `demo`, `label` `DEMO MODE — deterministic fixtures, no API key`, `database` `sqlite`.
- **Rewrite.** `curl -sS http://127.0.0.1:3000/madira-api/health` returns that same `demo_mode` and `label`.
- **Status.** `curl -sS http://127.0.0.1:8123/status` repeats the health fields and adds `specialists`: `menu-analyst`, `pairing-sommelier`, `list-curator`, `inventory-purchasing`, `staff-trainer`, `supplier-scheduler`. `wiring.specialists` matches that list and `wiring.has_task_tool` is true. `sample_menu` is present (347 characters on this seed).
- **Banner.** Open `/` and wait until `[data-testid=mode-banner]` does not contain `connecting`. It reads `DEMO MODE` and `deterministic fixtures, no API key`.
- **Doctor.** `make doctor` prints the same demo payload, then the live `/health` body, then `frontend ok`.
- **Proof.** Save the three response bodies. A banner screenshot is the user-visible half.

## Gotchas

- `/health` does not include `specialists`. Use `/status` for that list.
- `make doctor` glues `frontend ok` onto the same line as the `/health` JSON. The frontend check still passed when that line ends in `frontend ok`.
- Status is public. It includes the sample menu text. It does not include a provider key.
- `database` is `sqlite` for the default file. This run did not set `DATABASE_URL`.
