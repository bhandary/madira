# Audit

Audit is a read-only set of compliance tables. It is not the hash-chained ledger on Records. Each query is a table with totals and links back into the floor.

## Sub-features

- `audit-stock` is the default query, stock and depletion.
- `audit-kinds` switches the table among excursions, licenses, POS gaps, list versions, purchases, and audit events.

## How to get to it (user POV)

- Choose `Audit` in the sidebar or in `More`, or open `http://127.0.0.1:3000/audit`.
- Source: `frontend/src/app/audit/page.tsx`, `frontend/src/components/AuditorTable.tsx`.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`.

- **Stock.** Open `/audit`. The heading is `Audit`. The lead says the tables are read-only. `[data-testid=audit-kind]` is `stock` and its label is `Stock and depletion`. `[data-testid=auditor-row]` is visible. `[data-testid=auditor-totals]` is visible.
- **Link.** The first `[data-testid=auditor-link]` is `/inventory?sku=W-MUS-01`. Following it opens Inventory.
- **Read back.** `curl -sS 'http://127.0.0.1:8123/audit/queries/stock'` returns `audit_table` with rows. The other kind ids are `conditions`, `compliance`, `pos`, `lists`, `purchases`, and `events`.
- **Proof.** Screenshot the stock table before following the link.

## Gotchas

- Records (`/records`) is the vault, the hash chain, and the audit-pack download. This page does not upload a document.
- The floor chat can still name `compliance-auditor`. That reply is not this table.
