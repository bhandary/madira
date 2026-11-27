# Usage

Usage shows what the floor has spent and lets an Owner set a monthly cap and a request rate. The numbers are cents and requests, not a model invoice.

## Sub-features

- `usage-spent` reads the current month.
- `usage-limits` saves a cap and a per-minute limit.

## How to get to it (user POV)

- Choose `Usage` in the sidebar or in `More`, or open `http://127.0.0.1:3000/usage`.
- Source: `frontend/src/app/usage/page.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. `[data-testid=usage-save]` is enabled.

- **Read.** Open `/usage`. The heading is `Usage`. `[data-testid=usage-spent]` reads like `2026-11 · spent 0 cents · 0 micro-dollars · demo`.
- **Save.** Fill `[data-testid=usage-cap]` with `500` and `[data-testid=usage-rpm]` with `30`. Choose `[data-testid=usage-save]`. `[data-testid=usage-cap-status]` is `Cap 500 cents. Spent 0 cents. Limit 30 requests per minute. 0 used.`
- **Read back.** `curl -sS http://127.0.0.1:8123/usage` includes `monthly_spend_cap_cents` 500 and `requests_per_minute` 30.
- **Restore.** Clear both fields and save again if a later recipe needs the uncapped demo. An empty field turns that limit off.
- **Proof.** Screenshot the cap status after the save.

## Gotchas

- The save rejects a non-integer. The error text is `Use whole numbers, or leave a field empty to turn that limit off.`
- Usage does not call a provider. Demo mode still records the counters.
