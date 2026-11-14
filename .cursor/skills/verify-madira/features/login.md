# Sign in

Sign in explains that the floor works without an account. With Google unset, the page shows a not-configured notice and no Google button. Opening the Google start URL comes back to this page with the same notice plus an error.

## Sub-features

- `login-signed-out` shows the Sign in link in the sidebar.
- `login-unconfigured` shows the not-configured notice and hides the Google button.
- `login-start` sends `/madira-api/auth/google` back to `/login?error=not_configured`.
- `login-error` shows a fixed message for `error=state` and a generic failure for any other query value.

## How to get to it (user POV)

- Choose `Sign in` in the sidebar (`[data-testid=sign-in-link]`), or open `http://127.0.0.1:3000/login`.
- The sidebar link is not one of the seven section links. It sits in `[data-testid=account-menu]`.
- On a narrow viewport, choose `Sections`. The account block is inside `[data-testid=mobile-menu]`.

## Driving it with Playwright and curl

Preconditions:

- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MADIRA_AUTH_SECRET`, and `MADIRA_PUBLIC_URL` are unset, and the backend was started that way.
- No `madira_session` cookie.

- **Config.** `curl -sS -D- http://127.0.0.1:8123/auth/config` is 200 and `{"configured":false}`. `curl -sS http://127.0.0.1:8123/auth/me` is `{"user":null}`.
- **Notice.** Open `/login`. The heading is `Sign in`. Wait until `[data-testid=login-unconfigured]` is visible. Its text is `Google sign-in isn't configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, MADIRA_AUTH_SECRET, and MADIRA_PUBLIC_URL on the backend, then restart it.` `[data-testid=google-sign-in]` has count 0. The sidebar `[data-testid=sign-in-link]` still reads `Sign in`.
- **Start URL.** `curl -sS -D- -o /dev/null http://127.0.0.1:8123/auth/google` is `302` and `Location: /login?error=not_configured`. Open `http://127.0.0.1:3000/madira-api/auth/google`. The browser lands on `http://127.0.0.1:3000/login?error=not_configured`. `[data-testid=login-error]` is `Google sign-in isn't configured.` The unconfigured notice is still there.
- **Known error.** Open `/login?error=state`. `[data-testid=login-error]` is `That sign-in attempt expired. Try again.`
- **Rejected query.** Open `/login?error=%3Cscript%3Ealert(1)%3C/script%3E`. `[data-testid=login-page]` does not contain `<script>`. `[data-testid=login-error]` is `Sign-in failed. Try again.`
- **Proof.** Screenshot the unconfigured page and the page after the Google start URL.

## Gotchas

- A configured Google button (`[data-testid=google-sign-in]`, href `/madira-api/auth/google`, label `Continue with Google`) did not appear. Completing Google sign-in needs the four backend variables, a matching `MADIRA_PUBLIC_URL`, and a Google account. This run did not have them.
- Signed-in name, avatar, and `[data-testid=sign-out]` were not on the page. `GET /auth/me` returned `user: null`.
- The notice and the `error=not_configured` alert are different elements. Both were visible together after the redirect.
