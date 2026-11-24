# Purchasing and receiving

Purchasing drafts a purchase order by the case, waits for the Owner, and archives a PDF when the order is marked sent. It does not email the supplier. A sent order can take an invoice photo and a counted delivery. Accepting the delivery adds the counted bottles to the cellar.

## Sub-features

- `purchasing-suppliers` lists the seeded importers with case size, minimum, and a contact.
- `purchasing-draft` rounds bottles up to a case and saves a draft.
- `purchasing-approve` records the Owner's approval.
- `purchasing-send` marks the order sent and vaults a PDF.
- `receiving-invoice` uploads an invoice against that order.
- `receiving-accept` counts the line, accepts the delivery, and increases on-hand.

## How to get to it (user POV)

- Choose `Purchasing` in the sidebar, or open `http://127.0.0.1:3000/purchasing`.
- On a narrow viewport, choose `More`, then `Purchasing`.
- Receiving is the `Receive delivery` block on a sent or part-received order. It is not its own nav item.

## Driving it with Playwright and curl

Preconditions:

- Demo mode banner is past `connecting`. The demo Owner can approve. No Google session is required.
- Note `W-MUS-01` on-hand before accepting a delivery. The receive below adds 12.
- Kermit Lynch Wine Merchant is seeded at case size 12, minimum `$500.00` (50000 cents), delivery days `Tue, Thu`, contact `Claire Vasseur`.

- **Directory.** Open `/purchasing`. The heading is `Purchasing`. The lead says sending archives the PDF and does not email the supplier. The Kermit `[data-testid=supplier-card]` shows `Case 12`, `$500.00 minimum`, `Tue, Thu`, and `[data-testid=supplier-contact]` `Claire Vasseur`.
- **Draft math.** Choose `Kermit Lynch Wine Merchant` in `[data-testid=draft-supplier]`. Leave bottles at `6` and unit cost at `1800`. `[data-testid=draft-cases]` contains `1 case of 12`. `[data-testid=draft-quantity]` contains `12 bottles · $216.00`. `[data-testid=draft-minimum]` contains `Minimum not met · short $284.00`. `[data-testid=draft-delivery]` is a `YYYY-MM-DD` date on a Tuesday or Thursday. From a run on 2026-11-24 it was `2026-12-01`.
- **Draft.** Choose `[data-testid=draft-submit]`. `[data-testid=po-detail]` `[data-testid=po-status]` stores `draft`. The badge's CSS uppercases it, so the visible text is `DRAFT`. `[data-testid=approval-card]` is visible. `[data-testid=po-lines]` contains `W-MUS-01 Muscadet Domaine de l'Ecu` and `1 cases · 12 bottles · $216.00`. The line always says `cases`, including for one case.
- **Approve.** Fill `[data-testid=po-comment]` with `Send the Tuesday truck.` Choose `[data-testid=po-approve]`. The stored status is `approved` and the badge reads `APPROVED`. `[data-testid=approval-decision]` contains `approved` and the comment.
- **Send.** Choose `[data-testid=po-send]` (`Archive PDF & Mark Sent`). The stored status is `sent` and the badge reads `SENT`. `[data-testid=po-pdf]` has a relative href `/madira-api/procurement/orders/<id>/pdf`. Prefix the frontend origin before requesting it (`http://127.0.0.1:3000` plus that path). The response is 200, `content-type` contains `application/pdf`, and the body starts with `%PDF-`.
- **Read back.** `curl -sS http://127.0.0.1:8123/procurement/orders` includes that order with `status` `sent` and a `pdf_document_id`. `GET /compliance/documents` includes a `po_pdf`.
- **Invoice.** On the sent order, fill `[data-testid=invoice-number]` with a new number, leave `[data-testid=invoice-date]` as today, fill `[data-testid=invoice-unit-cost]` with `1800`, and set `[data-testid=invoice-file]` to a small PDF (`%PDF-1.4` is enough). Choose `[data-testid=invoice-upload]`. `[data-testid=invoice-lines]` contains `W-MUS-01`. `[data-testid=invoice-document]` downloads the vaulted file.
- **Receive.** On `[data-testid=receiving-line]` for `W-MUS-01`, fill `[data-testid=counted-qty]` with `12`. Choose `[data-testid=stage-receipt]`. If `[data-testid=receipt-flag]` is present, check `[data-testid=acknowledge-discrepancies]`. Choose `[data-testid=accept-delivery]`. The stored status is `received` and the badge reads `RECEIVED`. With the invoice unit cost at `1800`, matching the PO, no receipt flag appears.
- **Stock.** `GET /inventory` shows `W-MUS-01` `on_hand` increased by 12 from the number you noted. `GET /procurement/receipts` includes the receipt. `GET /procurement/invoices` includes the invoice number.
- **Proof.** Screenshot the draft status, the sent status with the PDF link, and the received status.

## Gotchas

- `Draft POs from low stock` (`[data-testid=draft-from-reorder]`) writes one order per supplier that is under par. The manual draft above is one Kermit line. Do not require four orders from the manual button.
- The bottle-count drafts from the Inventory specialist are `GET /purchase-orders`. This page reads `GET /procurement/orders`. An empty purchasing list does not mean the specialist drafts are missing.
- Receive delivery is hidden until the status is `sent` or `part_received`. Approve and send first.
- A counted quantity that does not match the order, or an invoice cost that does not match the PO, raises `[data-testid=receipt-flag]`. Accept stays blocked until `[data-testid=acknowledge-discrepancies]` is checked.
- Sending does not transmit email. There is no mailto link and no supplier inbox to watch.
- `Close PO` appears after `received`. Cancel appears on `draft` and `approved`. Neither is required to prove the PDF or the receipt.
