# Records

Records shows an append-only hash-chained audit ledger, a document vault, a retention period, and an audit-pack export. The floor can also ask the compliance auditor, who only reads.

## Sub-features

- `records-chain` shows the ledger and a Verified badge.
- `records-vault` uploads a file and downloads the same bytes.
- `records-retention` saves a new year count and puts 7 back.
- `records-pack` previews the pack and downloads the zip, the journal CSV, and the summary PDF.
- `records-auditor` delegates a storage-zone question to `compliance-auditor`.

## How to get to it (user POV)

- Choose `Records` in the sidebar, or open `http://127.0.0.1:3000/records`.
- On a narrow viewport, choose `More`, then `Records`.
- The auditor has no nav item. Ask from the floor chat.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. The demo Owner can edit retention (`[data-testid=retention-save]` is on the page).
- A fresh seed already has `[data-testid=chain-status]` `Verified` and a document row `maison-madira-liquor-license.txt`. `[data-testid=retention-years]` is `7`.
- The audit pack's default range is wide enough to include the seed (about 400 days back through today). Leave those dates unless you are checking an empty window.

- **Ledger.** Open `/records`. The heading is `Records`. `[data-testid=chain-status]` text is `Verified`. The badge class uppercases it, so `innerText` reads `VERIFIED`. `[data-testid=audit-table]` has column headings Seq, When, Actor, Action, Entity, Before / after.
- **Vault.** Choose type `Delivery note` in `[data-testid=vault-doc-type]`. Set `[data-testid=vault-file]` to a text file whose body is `Received 6 cases of Muscadet for the vault.` Choose `[data-testid=vault-upload]`. A `[data-testid=document-row]` shows that filename, a `[data-testid=document-sha]` whose `data-sha` is 64 hex characters, and a size. `[data-testid=audit-table]` contains `document.store`. Follow `[data-testid=document-download]`. The response is 200 and the body is the sentence you uploaded.
- **Filter.** Fill `[data-testid=audit-action]` with `document.store` and choose `[data-testid=audit-filter]`. The first `[data-testid=audit-row]` contains `document.store`. Clear the action and filter again to see the rest of the ledger.
- **Retention.** Fill `[data-testid=retention-years]` with `9` and choose `[data-testid=retention-save]`. Wait until the field's value is `9` before changing it again. The table contains `retention.update`. Fill `7`, save, and wait until the value is `7`. A second save started while the first refresh is still in flight can leave the field on the previous number. `GET /compliance/retention` then has `document_retention_years` 7 and `can_edit` true.
- **Pack.** `[data-testid=audit-pack]` is on the page after load, without an extra click: valuation, purchases, invoices, variance, waste, retention `7`, and chain `Verified` (`audit-pack-valuation`, `audit-pack-purchases`, `audit-pack-invoices`, `audit-pack-variance`, `audit-pack-waste`, `audit-pack-retention`, `audit-pack-chain`). The dollar and bottle figures follow the stock and the orders already in the database. Do not freeze them. The download hrefs are relative (`/madira-api/compliance/audit-pack` and the journal and summary paths). Prefix the frontend origin before requesting them. `[data-testid=download-audit-pack]` returns 200, `content-type` `application/zip`, and the body starts with `PK`. `[data-testid=download-journal-csv]` is `text/csv` and contains `Date,Reference,Description,Account,Debit,Credit,Supplier,Currency,DocumentHash`. `[data-testid=download-summary-pdf]` is `application/pdf` and starts with `%PDF-`.
- **Read back.** `curl -sS http://127.0.0.1:8123/compliance/audit-events/verify` is `valid` true. `GET /compliance/documents` includes the uploaded filename and the demo license.
- **Auditor.** Open `/` in a new browser context. Send `Report storage zone conditions.` The floor has no delegation rail. The proof is the last `[data-testid=copilot-assistant-message]`: it names `compliance-auditor` and says nothing was emailed or purchased. The reply contains a `[data-testid=zone-card]` for `Main Cellar` and one for `Bar & Cold Box`. `[data-testid=delegate-compliance-auditor]` exists on a workbench page, not on the floor.
- **Proof.** Screenshot the Verified badge with the uploaded row, and the zone card in the floor reply.

## Gotchas

- The chain badge says `Broken` only when a hash does not match. A demo seed is `Verified`. Do not edit `audit_events` to force a break during this drive.
- Retention outside 1–25 is rejected. Put the field back to `7` before you stop so the next drive sees the seed default.
- The auditor is read-only. A floor message does not create a zone, a reading, or an export. Log readings on [Inventory](./inventory.md).
- `next dev` may add the upgrade heading inside the overlay. The records page's own level-1 heading is `Records`.
