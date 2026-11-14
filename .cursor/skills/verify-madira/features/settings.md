# Settings

Settings is where a provider key would leave demo mode. With `MADIRA_ADMIN_PASSWORD` unset, the page stays on the password form and both the page and the API refuse the unlock.

## Sub-features

- `settings-locked` shows the password form and names `MADIRA_ADMIN_PASSWORD`.
- `settings-refuse` returns 403 for a password attempt and for a settings read with no token.
- `settings-stay` leaves the unlocked controls off the page.

## How to get to it (user POV)

- Choose `Settings` in the sidebar, or open `http://127.0.0.1:3000/settings`.
- On a narrow viewport, choose `Sections`, then `Settings`.

## Driving it with Playwright and curl

Preconditions:

- `MADIRA_ADMIN_PASSWORD` is unset and the backend was started that way.
- Demo mode banner is past `connecting`.

- **Read without a token.** `curl -sS -D- http://127.0.0.1:8123/settings/llm` is 403 and `detail` is `Set MADIRA_ADMIN_PASSWORD to manage LLM settings. Add it to the environment and restart the backend.`
- **Password attempt.** `curl -sS -D- -H 'Content-Type: application/json' -d '{"password":"not-the-password"}' http://127.0.0.1:8123/settings/session` is the same 403 and the same `detail`.
- **Page.** Open `/settings`. `[data-testid=settings-page]` is visible. The heading is `Settings`. The copy says the key is encrypted and never shown again, and that settings are locked with `MADIRA_ADMIN_PASSWORD`. `[data-testid=settings-password]` and `[data-testid=settings-unlock]` are visible. `[data-testid=settings-mode]` is absent.
- **Unlock.** Fill `[data-testid=settings-password]` with `not-the-password` and choose `[data-testid=settings-unlock]`. `[data-testid=settings-error]` is the same 403 sentence. The password form remains. The banner still reads `DEMO MODE`.
- **Proof.** Screenshot the error under the unlock button, with the demo banner still visible.

## Gotchas

- The unlocked form (`[data-testid=settings-mode]`, `[data-testid=settings-key-hint]`, `[data-testid=settings-provider]`, `[data-testid=settings-model]`, `[data-testid=settings-api-key]`, `[data-testid=settings-save]`, `[data-testid=settings-remove]`, `[data-testid=settings-lock]`) is in the page source and was not reached. Reaching it needs `MADIRA_ADMIN_PASSWORD` set on the backend process before startup. This run did not set it, and did not save a provider key.
- A wrong password and a missing password are not distinguished while the variable is unset. Both are the 403 sentence above. Do not look for the word `incorrect` on this baseline.
- Google sign-in does not unlock this page. The login feature and this one stay separate.
