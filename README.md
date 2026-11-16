# Madira

Maison Madira's beverage-program desk: a Head Sommelier agent that delegates to specialists and renders **A2UI** surfaces (pairing cards, list tables, inventory, quizzes, tasting drafts) instead of chat walls.

The app is aimed at restaurants. It runs in a clearly labeled **DEMO MODE** with a deterministic fake model when no LLM API key is set.

## Architecture

```mermaid
flowchart TD
  UI["Next.js + Tailwind<br/>CopilotKit AG-UI + A2UI catalog"]
  Runtime["CopilotKit runtime<br/>/api/copilotkit"]
  REST["FastAPI REST<br/>/agent/run · CRUD"]
  AGUI["AG-UI bridge<br/>/ag-ui"]
  Head["Head Sommelier<br/>deepagents.create_deep_agent"]
  Task["task tool"]
  MA["menu-analyst"]
  PS["pairing-sommelier"]
  LC["list-curator"]
  IP["inventory-purchasing"]
  ST["staff-trainer"]
  SS["supplier-scheduler"]
  DB["SQLite default<br/>DATABASE_URL → Postgres"]

  UI --> Runtime
  UI --> REST
  Runtime --> AGUI
  AGUI --> Head
  REST --> Head
  Head --> Task
  Task --> MA
  Task --> PS
  Task --> LC
  Task --> IP
  Task --> ST
  Task --> SS
  MA --> DB
  PS --> DB
  LC --> DB
  IP --> DB
  ST --> DB
  SS --> DB
```

### Delegation map

The orchestrator never does specialist work. It calls Deep Agents' **`task`** tool with `subagent_type`:

| Subagent | When | A2UI surface |
| --- | --- | --- |
| `menu-analyst` | Menu PDF / image / pasted text | `DishList` |
| `pairing-sommelier` | Pairings per dish (wine, beer, spirit, sake) | `PairingGrid` |
| `list-curator` | Budget + target pour/bottle margin | `BeverageListTable` + `ListSummary` |
| `inventory-purchasing` | Stock, par, depletion, draft POs | `InventoryTable` + `PurchaseOrderTable` |
| `staff-trainer` | Lessons, briefing, quiz, diner roleplay | `LessonCards` + `QuizCard` |
| `supplier-scheduler` | Importer/distributor tastings | `ScheduleForm` + `TastingCalendar` (.ics draft only) |

Delegation is visible in the right-hand rail (active subagent, status, todo list).

## Stack

- **Frontend:** Next.js, TypeScript, Tailwind, CopilotKit (`@copilotkit/react-core`, `@copilotkit/runtime`) over AG-UI, A2UI v0.9 catalog + renderer.
- **Backend:** Python FastAPI, LangChain **Deep Agents** (`deepagents.create_deep_agent`, `subagents=` → `task` tool).
- **Data:** SQLAlchemy. Schema is managed by Alembic (`backend/madira/migrations`). Unset `DATABASE_URL` uses `sqlite:///backend/data/madira.db` (tests and CI). Dev and prod set `DATABASE_URL=postgresql+psycopg://…`.

## Environment

See `.env.example`.

| Variable | Default | Notes |
| --- | --- | --- |
| `MADIRA_LLM_PROVIDER` | `openai` | Also `anthropic`, `google_genai` |
| `MADIRA_LLM_MODEL` | `gpt-4.1-mini` | Provider model id |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `MADIRA_API_KEY` | empty | If unset, **DEMO MODE** |
| `MADIRA_DEMO_MODE` | auto | `true` forces fixtures even if a key is saved; `false` requires a key |
| `MADIRA_SECRET_KEY` | dev file | Fernet key (or any secret) for keys saved in Settings. If unset, `backend/data/.madira_secret` is created. Set this in production. |
| `MADIRA_OWNER_EMAIL` | unset | Google account that becomes Owner of the default venue on sign-in. Settings, billing, and model keys require Owner. |
| `MADIRA_FRONTEND_ORIGIN` | `http://localhost:3000` | Only this origin is allowed by CORS, with credentials. |
| `DATABASE_URL` | sqlite file | Postgres URL for dev and prod. Unset keeps SQLite. |
| `MADIRA_BACKEND_URL` | `http://127.0.0.1:8123` | Used by Next rewrites / CopilotKit HttpAgent |
| `MADIRA_PORT` | `8123` | Backend |
| `GOOGLE_CLIENT_ID` | unset | Google OAuth client id. Sign-in stays disabled until this is set. |
| `GOOGLE_CLIENT_SECRET` | unset | Google OAuth client secret. Backend only. |
| `MADIRA_AUTH_SECRET` | unset | HMAC secret for the sign-in session cookie. |
| `MADIRA_PUBLIC_URL` | unset | Browser origin, no path. Used as the OAuth redirect base. |

Demo mode uses `DemoChatModel`: it inspects the user message, emits `write_todos` + `task` calls, and specialists run deterministic tools against fixtures. No secrets required.

## Settings

Open **Settings** in the nav to leave demo mode without editing a file or restarting.

1. Sign in as the Owner. In demo mode (no provider key in the environment) the floor runs as the demo Owner, so Settings opens directly. Outside demo mode, a request with no session is 401, and any other role is 403.
2. Choose OpenAI, Anthropic, or Google, optionally a model, and paste an API key. The backend sends one 1-token request to that model before saving, so a key with no credits, quota, or permission is rejected. A rejected key is not stored. If a later sommelier run still fails (rate limit, billing, auth), the page shows that provider message. The API key is never included.
3. The key is encrypted with Fernet (`MADIRA_SECRET_KEY`, or the dev fallback file) and stored for the Owner's organization. The API returns only a hint such as `ends in …abcd`. Saving or removing a key rebuilds the sommelier immediately.

Precedence: a saved key overrides `MADIRA_LLM_PROVIDER`, `MADIRA_LLM_MODEL`, and the provider API keys. Removing it falls back to those environment variables, then to demo mode. `MADIRA_DEMO_MODE=true` still forces demo.

`MADIRA_LLM_VALIDATOR=accept` skips the provider check. Use it only for local tests when you do not have a real key. Do not set it in production.

The Settings end-to-end test runs in demo mode, as the demo Owner. It needs `MADIRA_LLM_VALIDATOR=accept` on the backend if you are not using a real key.

## Sign in

`/login` offers **Continue with Google**. In demo mode the floor, including chat and Settings, runs as the demo Owner without a Google session. Outside demo mode, data routes require a session. When `MADIRA_OWNER_EMAIL` is set, that Google account receives the Owner membership on the default venue at sign-in. Settings, billing, and model keys are Owner only.

The browser only talks to the Next.js origin. `/madira-api/*` is already rewritten to FastAPI, so the authorization code is exchanged there and the session cookie is first-party (`madira_session`, HttpOnly, SameSite=Lax, Secure when `MADIRA_PUBLIC_URL` is https, 14 days). Sign out is `POST /auth/logout`.

On the first successful sign-in the backend inserts a `users` row (`google_sub` unique, email, name, picture, `created_at`, `last_login_at`). Later sign-ins update that row. Alembic creates that table with the rest of the schema (`make migrate`, or automatically when the backend starts).

Set these on the **backend** service (Railway's API service, not only `madira-web`):

| Variable | Example |
| --- | --- |
| `GOOGLE_CLIENT_ID` | from Google Cloud |
| `GOOGLE_CLIENT_SECRET` | from Google Cloud |
| `MADIRA_AUTH_SECRET` | long random string |
| `MADIRA_PUBLIC_URL` | `http://localhost:3000` or `https://madira-web-production.up.railway.app` |

`MADIRA_PUBLIC_URL` is the origin only: scheme, host, optional port, no path, no trailing slash. If any of the four is missing, or the public URL is not an origin, `/login` says Google sign-in isn't configured and `/auth/google` redirects back there instead of raising.

In Google Cloud, create an OAuth client of type **Web application**. The consent screen needs the non-sensitive scopes `openid`, `email`, and `profile`. Authorized redirect URIs, exactly:

```text
http://localhost:3000/madira-api/auth/callback
http://127.0.0.1:3000/madira-api/auth/callback
https://madira-web-production.up.railway.app/madira-api/auth/callback
```

`MADIRA_PUBLIC_URL` has to be the origin you are actually browsing. Playwright and `make doctor` use `http://127.0.0.1:3000`, so local sign-in from that host needs `MADIRA_PUBLIC_URL=http://127.0.0.1:3000`. Production:

```text
MADIRA_PUBLIC_URL=https://madira-web-production.up.railway.app
```

The flow is the authorization code grant with S256 PKCE, `state`, and `nonce`. The ID token is checked (RS256 signature against Google's JWKS, issuer, audience, expiry, nonce, `email_verified`) before the user row is written. The cookie is an HMAC of the Google subject, not the Google token.

## Local run

```bash
make install
make dev          # backend :8123 + frontend :3000
```

Or separately: `make backend` and `make frontend`.

One-shot doctor: `make doctor` (expects both processes).

`make dev` leaves `DATABASE_URL` unset, so it uses the SQLite file. Postgres for local dev:

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+psycopg://madira:madira@localhost:5432/madira
make migrate       # optional; backend startup applies migrations too
make dev
```

`docker compose up --build` starts Postgres and points the backend at it. A SQLite file created before Alembic has tables and no revision row. Remove it with `make clean` before starting again.

## Tests

```bash
make test         # Deep Agents wiring: specialists exposed, task delegation, A2UI ops
cd frontend && npx playwright test
```

Project-local verification skill: [`.cursor/skills/verify-madira/SKILL.md`](.cursor/skills/verify-madira/SKILL.md).

## Product

1. **Menu upload** — PDF, image, or paste → dishes → pairings across four beverage types with rationale and price-tier fit.
2. **List curation** — budget + target margin, coverage, gaps, cost/margin math.
3. **Inventory** — on-hand, par, depletion, low-stock, draft POs by supplier (seeded cellar).
4. **Staff training** — wine knowledge, etiquette, daily briefing, scored quiz, diner roleplay.
5. **Supplier meetings** — draft tastings, calendar, `.ics` export. **Never sends email or invites.**
