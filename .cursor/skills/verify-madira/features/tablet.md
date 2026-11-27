# Tablet

A shared tablet lets the people on the roster unlock the floor with a PIN. Enabling it replaces the signed-in person with the picker. The auto-lock returns to the picker after the idle window.

## Sub-features

- `tablet-pin` stores a PIN for the current person.
- `tablet-share` turns the picker on and unlocks another person.
- `tablet-lockout` locks the picker after repeated wrong PINs.

## How to get to it (user POV)

- The PIN field is on every page once a person is signed in (`[data-testid=my-pin]`).
- The Owner turns sharing on from `[data-testid=tablet-settings]` on `/settings`.
- Source: `frontend/src/components/TabletMode.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. The active persona is the Owner.
- Clear Ana's stored PIN first if `[data-testid=tablet-clear-row][data-name=Ana]` is present: choose its `[data-testid=tablet-clear-pin]`.

- **Pins.** On `/settings`, fill `[data-testid=my-pin]` with `1357` and choose `[data-testid=my-pin-save]`. `[data-testid=my-pin-saved]` is visible. Switch to Ana (`POST /auth/demo-persona` `{"slug":"ana"}`), open `/`, and save `2468` the same way. Switch back to `owner` and open `/settings`.
- **Share.** Choose `[data-testid=tablet-enable]`. `[data-testid=tablet-picker]` is visible. Choose `[data-testid=tablet-person][data-name=Ana]`, enter `2468` with `[data-testid=tablet-digit-2]`, `4`, `6`, and `8`, and choose `[data-testid=tablet-pin-submit]`. `[data-testid=tablet-actor]` reads `Signed in as Ana` and a `Switch` control.
- **Wrong PIN.** From the picker, enter `0000` and submit five times. `[data-testid=tablet-pin-error]` contains `locked`. The correct PIN then stays locked for that window.
- **Read back.** `curl -sS http://127.0.0.1:8123/tablet` includes `enabled` true after the share.
- **Restore.** End the shared session from `[data-testid=tablet-settings]` `[data-testid=tablet-end]`. The picker mounts a second button with the same test id, so an unscoped click matches two. Switch the persona back to `owner`.
- **Proof.** Screenshot the picker and the `Signed in as Ana` line.

## Gotchas

- The idle lock in the product test advances a fake clock by 16 minutes. A live drive that does not install a clock should not wait that out. The unlock and the wrong-PIN lock are the proof.
- Do not leave the tablet enabled. Staff routes hide the rest of the floor.
