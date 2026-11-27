# Floor lookup

Lookup answers a dish, bottle, or preference from the published list and the cellar. The same query works from the cached pack when the phone is offline.

## Sub-features

- `lookup-search` submits a query and lists hits.
- `lookup-pack` downloads the pack on load so a later offline search still returns a hit.

## How to get to it (user POV)

- On Tonight, choose `Lookup`, or open `http://127.0.0.1:3000/lookup`.
- The desktop sidebar link is `Lookup`.
- A Staff phone tab is `Lookup`. An Owner phone reaches it from the Tonight button, not from the tab bar.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.
- Source: `frontend/src/app/lookup/page.tsx`, `frontend/src/components/FloorLookup.tsx`.

- **Search.** Open `/lookup`. The heading is `Floor lookup`. Fill `[data-testid=lookup-query]` with `Chablis` and choose `[data-testid=lookup-submit]`. A `[data-testid=lookup-result]` contains `Chablis`. `[data-testid=lookup-glassware]` is `White wine glass`. `[data-testid=lookup-temperature]` is `10–12°C`. `[data-testid=lookup-pour]` is `150 ml`. `[data-testid=lookup-stock]` is not empty.
- **Offline.** After the page has requested `/lookup/pack` (the load does this), set the browser context offline, fill `Chablis` again, and submit. A result containing `Chablis` is still visible and `[data-testid=offline-banner]` is visible. Set the context online again before the next recipe.
- **Read back.** `curl -sS 'http://127.0.0.1:8123/lookup?q=Chablis'` returns hits. `GET /lookup/pack` returns the pack the page caches.
- **Proof.** Screenshot the Chablis result with the glassware line visible.

## Gotchas

- The temperature and pour strings are `10–12°C` and `150 ml`. They are not the list page's `45-50°F` and `5 oz`.
- A Staff persona who opens `/menu` is sent back to Tonight. Lookup itself stays available.
