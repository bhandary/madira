# Team

The team tab on Staff training is the roster, the invites, the progress list, and the certificate file. Scored roleplay lives on the practice tab. A Manager sees the expiring certificate on Tonight.

## Sub-features

- `team-invite` adds a pending invite for a new email.
- `team-roleplay` runs the skeptic guest and shows a four-part rubric.
- `team-certificate` files a card that Tonight lists before it expires.

## How to get to it (user POV)

- Open `http://127.0.0.1:3000/training` and choose `Team`.
- Practice is the `Practice` tab on the same page.
- Source: `frontend/src/app/training/page.tsx`, `frontend/src/components/TeamDesk.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. `[data-testid=training-actor]` contains `Demo Owner`.
- Switch personas with `POST /auth/demo-persona` and `{"slug":"ana"}`, `{"slug":"mia"}`, or `{"slug":"owner"}`. The demo people are seeded.

- **Invite.** Choose `[data-testid=tab-team]`. Fill `[data-testid=invite-email]` with a new address, set `[data-testid=invite-role]` to `Staff` and `[data-testid=invite-position]` to `server`, and choose `[data-testid=invite-submit]`. An `[data-testid=invite-row]` contains that address.
- **Certificate.** Set `[data-testid=certificate-user]` to `Mia`, `[data-testid=certificate-kind]` to `responsible_service`, `[data-testid=certificate-label]` to `Responsible service`, an issued date about 20 days ago, and an expiry about 10 days ahead. Set `[data-testid=certificate-file]` to a small text file and choose `[data-testid=certificate-save]`. `[data-testid=certificate-expiring]` contains `Mia · Responsible service` and the expiry date.
- **Roleplay.** Switch to Ana and reload `/training`. `[data-testid=training-actor]` reads `Ana · Staff` and `[data-testid=tab-team]` is absent. Choose `[data-testid=tab-practice]`, then `[data-testid=roleplay-persona-skeptic]`, then `[data-testid=roleplay-start]`. `[data-testid=roleplay-guest]` is visible. Fill `[data-testid=roleplay-reply]` and choose `[data-testid=roleplay-send]`, then `[data-testid=roleplay-finish]`. `[data-testid=roleplay-rubric]` is visible, `[data-testid=roleplay-score]` reads `Score 3` for that reply, and `[data-testid=roleplay-criterion]` counts 4.
- **Manager.** Switch to Mia and reload `/training`. Choose `Team`. `[data-testid=progress-person]` contains `Ana` and `Roleplay 3.00`. On `/`, `[data-testid=tonight-certificate]` reads `Mia · Responsible service · Expires 2026-12-07` when the expiry was that date.
- **Restore.** Switch back to `owner` before the next Owner recipe.
- **Proof.** Screenshot the invite row, the rubric, and the Tonight certificate line.

## Gotchas

- Ana is Staff. The team tab and the desktop sidebar beyond Tonight, Lookup, and Lessons are hidden, and other routes redirect to `/`.
- The certificate expiry has to fall inside the reminder window. A date ten days out is the one the Tonight line uses.
