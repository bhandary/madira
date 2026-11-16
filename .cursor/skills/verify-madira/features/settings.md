# Settings

Settings is where an Owner saves a provider key and leaves the deterministic model. In demo mode the request is the demo Owner, so the key form is on the page. There is no shared password.

## Sub-features

- `settings-owner` shows the provider form for the Owner.
- `settings-save` stores a key and the banner leaves `DEMO MODE`.
- `settings-remove` deletes the key and the banner returns to `DEMO MODE`.

## How to get to it (user POV)

- Choose `Settings` in the sidebar, or open `http://127.0.0.1:3000/settings`.
- On a narrow viewport, choose `Sections`, then `Settings`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode: no provider key in the environment, `MADIRA_DEMO_MODE` unset.
- To save a fake key, the backend was started with `MADIRA_LLM_VALIDATOR=accept`.
- Demo mode banner is past `connecting`.

- **Read.** `curl -sS http://127.0.0.1:8123/settings/llm` is 200 and returns `mode` `demo` with an empty `key_hint`.
- **Page.** Open `/settings`. `[data-testid=settings-page]` is visible. The heading is `Settings`. The copy says model keys are limited to the Owner. `[data-testid=settings-mode]` reads `demo`. `[data-testid=settings-provider]`, `[data-testid=settings-model]`, `[data-testid=settings-api-key]`, `[data-testid=settings-save]`, and `[data-testid=settings-remove]` are visible. `[data-testid=settings-password]` is absent.
- **Save.** Choose provider `OpenAI`, fill `[data-testid=settings-api-key]` with a fake key, and choose `[data-testid=settings-save]`. `[data-testid=settings-mode]` becomes `live` and the banner leaves `DEMO MODE`.
- **Remove.** Choose `[data-testid=settings-remove]`. `[data-testid=settings-mode]` returns to `demo` and the banner reads `DEMO MODE` again.

## Gotchas

- Outside demo mode, a request with no session is 401 and the page shows `[data-testid=settings-signed-out]`. A signed-in role other than Owner is 403 and the page shows `[data-testid=settings-forbidden]`.
- A key saved here is the organization's key. It turns the model live. It does not turn off the demo Owner fallback; that fallback ends when `MADIRA_DEMO_MODE=false` or a provider key is set in the environment.
