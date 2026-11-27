# Settings

Settings is where an Owner saves a provider key and leaves the deterministic model. In demo mode the request is the demo Owner, so the key form is on the page. There is no shared password.

## Sub-features

- `settings-owner` shows the provider form for the Owner.
- `settings-save` stores a key and the banner leaves `DEMO MODE`.
- `settings-locked` reloads the page and shows the signed-out state, because the saved key turned the demo Owner off.

## How to get to it (user POV)

- Choose `Settings` in the sidebar, or open `http://127.0.0.1:3000/settings`.
- On a narrow viewport, choose `More`, then `Settings`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode: no provider key in the environment, `MADIRA_DEMO_MODE` unset.
- To save a fake key, the backend was started with `MADIRA_LLM_VALIDATOR=accept`.
- Demo mode banner is past `connecting`.

- **Read.** `curl -sS http://127.0.0.1:8123/settings/llm` is 200 and returns `demo_mode` true, `source` `demo`, `configured` false, `stored` false, `key_hint` null, and `label` `DEMO MODE — deterministic fixtures, no API key`.
- **Page.** Open `/settings`. `[data-testid=settings-page]` is visible. The heading is `Settings`. The copy says model keys are limited to the Owner. `[data-testid=settings-mode]` reads `DEMO MODE — deterministic fixtures, no API key` and `[data-testid=settings-key-hint]` reads `No key saved in Settings.` `[data-testid=settings-provider]`, `[data-testid=settings-model]`, `[data-testid=settings-api-key]`, `[data-testid=settings-save]`, and `[data-testid=settings-remove]` are visible. `Remove key` is disabled while nothing is stored. `[data-testid=settings-password]` is absent.
- **Save.** Choose provider `OpenAI`, fill `[data-testid=settings-api-key]` with a fake key such as `sk-verify-madira-1234`, and choose `[data-testid=settings-save]`. `[data-testid=settings-mode]` becomes `LIVE — openai:gpt-4.1-mini`. `[data-testid=settings-key-hint]` reads `Key set, ends in …1234`. The banner on this page stays `DEMO MODE`. `AppShell` reloads status on a pathname change or a `madira-status` event, and the save does not fire that event. `GET /health` after the save is `demo_mode` false and `label` `LIVE — openai:gpt-4.1-mini`.
- **Locked.** Reload `/settings`. `[data-testid=settings-signed-out]` is visible. `curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8123/settings/llm` is 401, and so are `/inventory`, `/menus`, `/lists`, `/products`, `/tastings`, `/suppliers`, `/purchase-orders`, `/procurement/orders`, `/inventory/counts`, `/compliance/audit-events`, and `/training/progress`. On `/`, fill `[data-testid=copilot-chat-textarea]`, choose `[data-testid=copilot-send-button]`, and `[data-testid=copilot-chat-error]` reads `HTTP 401: {"detail":"Sign in required."}`. A fresh load of the banner, now that `/status` is live, shows the mode word `LIVE` and the detail equal to the full label `LIVE — openai:gpt-4.1-mini`. The visible line is `LIVE` followed by `LIVE — openai:gpt-4.1-mini`. That doubled word is a product defect in `ModeBanner` (`frontend/src/components/AppShell.tsx`), which strips a `DEMO MODE` prefix and leaves a `LIVE` prefix in place. The correct label is the single string in `[data-testid=settings-mode]`. Do not treat the doubled word as the passing label, and do not rewrite this step so the doubled word is required.
- **Restore.** Stop the backend, delete the row (`backend/.venv/bin/python -c "import sqlite3; c = sqlite3.connect('backend/data/madira.db'); c.execute('delete from llm_credentials'); c.commit()"`), and start the backend again with the Launch command. `/health` is back to demo and a floor message gets the demo reply.

## Gotchas

- Outside demo mode, a request with no session is 401 and the page shows `[data-testid=settings-signed-out]`. A signed-in role other than Owner is 403 and the page shows `[data-testid=settings-forbidden]`.
- A key saved here is the organization's key. It turns the model live and turns off the demo Owner at the same time. The next request with no session is 401, including `DELETE /settings/llm`. Removing the key takes an Owner session. Deleting the row while the backend runs is not enough: `/health` went back to demo, but the next floor message still went to OpenAI with the fake key and failed with `Error code: 401 - Incorrect API key provided`. Restart the backend after the delete. `MADIRA_DEMO_MODE=true` still forces the fixture demo, saved key included.
