# Sourcing

Sourcing turns list gaps into a want list. Quantities come from the cellar. The note is a rationale, not an order.

## Sub-features

- `sourcing-build` creates a brief.
- `sourcing-history` lists past tastings under the brief.

## How to get to it (user POV)

- Choose `Sourcing` in the sidebar or in `More`, or open `http://127.0.0.1:3000/sourcing`.
- Source: `frontend/src/app/sourcing/page.tsx`, `frontend/src/components/SourcingViews.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.

- **Build.** Open `/sourcing`. The heading is `Sourcing`. The lead says gaps from the list become a want list. Choose `[data-testid=sourcing-build]`. `[data-testid=sourcing-brief]` is visible. If the list has a gap, a `[data-testid=want-item]` is visible and `[data-testid=want-quantity]` is not empty. `[data-testid=tasting-history]` is on the page.
- **Read back.** `curl -sS -X POST http://127.0.0.1:8123/sourcing/briefs` returns a brief. `GET /sourcing/briefs` lists it.
- **Proof.** Screenshot the brief after the build.

## Gotchas

- A fresh seed can have no gap, so the brief can render with an empty want list. The proof is the brief panel and the POST, not a particular product name.
- Building a brief does not create a purchase order.
