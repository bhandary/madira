"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, acceptReceipt, listBins, stageReceipt, type CellarBin, type InvoiceRecord } from "@/lib/api";

const FLAG_LABELS: Record<string, string> = {
  short: "Short",
  over: "Over",
  invoice_qty_mismatch: "Invoice Qty",
  vintage_substitution: "Vintage Sub",
  price_change: "Price Change",
};

export type ReceivingOrderLine = {
  id: string;
  sku: string;
  name?: string;
  product_name?: string;
  quantity_ordered: number;
  quantity_received?: number;
  unit_cost_cents: number;
  vintage?: string | null;
};

export type ReceivingOrder = {
  id: string;
  po_number?: string | null;
  supplier?: string;
  status?: string;
  lines?: ReceivingOrderLine[];
};

export type ReceivingLineView = {
  id?: string;
  po_line_id?: string | null;
  sku: string;
  product_name?: string;
  ordered_qty?: number;
  remaining_qty?: number;
  invoiced_qty?: number | null;
  counted_qty?: number;
  ordered_unit_cost_cents?: number;
  invoiced_unit_cost_cents?: number | null;
  ordered_vintage?: string | null;
  received_vintage?: string | null;
  bin_id?: string | null;
  flags?: string[];
  cost_delta_cents?: number;
};

export type ReceivingReceiptView = {
  id?: string;
  status?: string;
  invoice_id?: string | null;
  notes?: string | null;
  discrepancy_summary?: { has_discrepancies?: boolean; cost_delta_cents?: number };
  lines?: ReceivingLineView[];
};

function money(cents: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format((cents || 0) / 100);
}

function flagLabel(code: string) {
  return FLAG_LABELS[code] || code;
}

function rowsFromOrder(order: ReceivingOrder | null | undefined, invoice: InvoiceRecord | null | undefined): ReceivingLineView[] {
  const extracted = invoice?.extracted_lines || [];
  return (order?.lines || []).map((line) => {
    const match = extracted.find(
      (row) => row.po_line_id === line.id || row.sku.toUpperCase() === line.sku.toUpperCase(),
    );
    const ordered = Number(line.quantity_ordered) || 0;
    const received = Number(line.quantity_received) || 0;
    const remaining = Math.max(0, ordered - received);
    return {
      po_line_id: line.id,
      sku: line.sku,
      product_name: line.product_name || line.name || line.sku,
      ordered_qty: ordered,
      remaining_qty: remaining,
      invoiced_qty: match ? Number(match.quantity) : null,
      counted_qty: remaining,
      ordered_unit_cost_cents: line.unit_cost_cents,
      invoiced_unit_cost_cents: match ? Number(match.unit_cost_cents) : null,
      ordered_vintage: line.vintage || null,
      received_vintage: line.vintage || "",
      bin_id: "",
      flags: [],
      cost_delta_cents:
        match && Number(match.unit_cost_cents) !== line.unit_cost_cents
          ? Number(match.unit_cost_cents) - line.unit_cost_cents
          : 0,
    };
  });
}

export function ReceivingChecklist({
  purchaseOrder,
  invoice,
  receipt,
  lines,
  onUpdated,
}: {
  purchaseOrder?: ReceivingOrder | null;
  invoice?: InvoiceRecord | null;
  receipt?: ReceivingReceiptView | null;
  lines?: ReceivingLineView[] | null;
  onUpdated?: () => void;
}) {
  const seeded = useMemo(() => {
    if (lines && lines.length) return lines;
    if (receipt?.lines && receipt.lines.length) return receipt.lines;
    return rowsFromOrder(purchaseOrder, invoice);
  }, [lines, receipt, purchaseOrder, invoice]);
  const [rows, setRows] = useState<ReceivingLineView[]>(seeded);
  const [stagedId, setStagedId] = useState(receipt?.id || "");
  const [summary, setSummary] = useState(receipt?.discrepancy_summary || null);
  const [ack, setAck] = useState(false);
  const [notes, setNotes] = useState(receipt?.notes || "");
  const [bins, setBins] = useState<CellarBin[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listBins()
      .then((body) => {
        if (!cancelled) setBins(body.bins);
      })
      .catch(() => {
        if (!cancelled) setBins([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasFlags = rows.some((row) => (row.flags || []).length > 0) || Boolean(summary?.has_discrepancies);
  const canAccept = Boolean(stagedId) && !dirty && (receipt?.status || "draft") !== "accepted";

  function edit(index: number, patch: Partial<ReceivingLineView>) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch, flags: [] } : row)));
    setDirty(true);
    setAck(false);
    setError("");
  }

  async function stage() {
    if (!purchaseOrder?.id) return;
    setBusy(true);
    setError("");
    try {
      const staged = await stageReceipt(purchaseOrder.id, {
        invoice_id: invoice?.id || receipt?.invoice_id || null,
        notes: notes || null,
        lines: rows.map((row) => ({
          po_line_id: row.po_line_id || null,
          sku: row.sku,
          counted_qty: Number(row.counted_qty) || 0,
          received_vintage: row.received_vintage ? String(row.received_vintage) : null,
          bin_id: row.bin_id || null,
        })),
      });
      setRows(staged.lines);
      setStagedId(staged.id);
      setSummary(staged.discrepancy_summary);
      setDirty(false);
      setAck(false);
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "The delivery could not be staged.");
    } finally {
      setBusy(false);
    }
  }

  async function accept() {
    if (!stagedId) return;
    setBusy(true);
    setError("");
    try {
      await acceptReceipt(stagedId, { acknowledge_discrepancies: ack, notes: notes || null });
      onUpdated?.();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "The delivery could not be accepted.");
    } finally {
      setBusy(false);
    }
  }

  if (!rows.length) {
    return <p className="text-sm text-muted">This purchase order has no lines to receive.</p>;
  }

  return (
    <div className="min-w-0 space-y-3" data-testid="receiving-checklist">
      {rows.map((row, index) => {
        const flags = row.flags || [];
        const invoiced = row.invoiced_unit_cost_cents;
        const orderedCost = row.ordered_unit_cost_cents || 0;
        return (
          <article key={row.po_line_id || row.sku} className="panel min-w-0 p-3" data-testid="receiving-line" data-sku={row.sku}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="break-words text-sm font-medium">{row.product_name || row.sku}</h3>
              <span className="font-mono text-xs">{row.sku}</span>
            </div>
            <p className="mt-1 text-sm text-muted">
              Ordered {row.ordered_qty ?? "—"}
              {row.remaining_qty != null ? ` · still due ${row.remaining_qty}` : ""}
              {" · "}
              Invoiced {row.invoiced_qty == null ? "—" : row.invoiced_qty}
            </p>
            <p className="mt-1 text-sm">
              PO {money(orderedCost)}
              {invoiced != null ? ` · Invoice ${money(invoiced)}` : ""}
              {row.ordered_vintage ? ` · vintage ${row.ordered_vintage}` : ""}
            </p>
            <div className="mt-3 grid gap-3">
              <label className="lbl" htmlFor={`counted-${row.po_line_id || row.sku}`}>
                Counted bottles
                <input
                  id={`counted-${row.po_line_id || row.sku}`}
                  data-testid="counted-qty"
                  className="field w-full"
                  inputMode="decimal"
                  value={row.counted_qty ?? ""}
                  onChange={(event) => edit(index, { counted_qty: Number(event.target.value) })}
                />
              </label>
              <label className="lbl" htmlFor={`vintage-${row.po_line_id || row.sku}`}>
                Received vintage
                <input
                  id={`vintage-${row.po_line_id || row.sku}`}
                  data-testid="received-vintage"
                  className="field w-full"
                  value={row.received_vintage || ""}
                  onChange={(event) => edit(index, { received_vintage: event.target.value })}
                />
              </label>
              <label className="lbl" htmlFor={`bin-${row.po_line_id || row.sku}`}>
                Destination bin
                <select
                  id={`bin-${row.po_line_id || row.sku}`}
                  data-testid="receive-bin"
                  className="field w-full"
                  value={row.bin_id || ""}
                  onChange={(event) => edit(index, { bin_id: event.target.value })}
                >
                  <option value="">Main cellar</option>
                  {bins.map((bin) => (
                    <option key={bin.id} value={bin.id}>
                      {bin.code}
                      {bin.label ? ` · ${bin.label}` : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {flags.length ? (
              <ul className="mt-3 flex flex-wrap gap-1.5" data-testid="line-flags">
                {flags.map((flag) => (
                  <li key={flag} className="badge badge-alert" data-testid="receipt-flag">
                    {flagLabel(flag)}
                  </li>
                ))}
              </ul>
            ) : null}
            {flags.includes("price_change") && row.cost_delta_cents ? (
              <p className="mt-2 text-sm" data-testid="cost-delta">
                Price change {money(row.cost_delta_cents)}
              </p>
            ) : null}
          </article>
        );
      })}
      {purchaseOrder?.id ? (
        <button type="button" className="btn btn-secondary w-full" data-testid="stage-receipt" disabled={busy} onClick={() => void stage()}>
          Stage delivery
        </button>
      ) : null}
      {hasFlags && !dirty && stagedId ? (
        <label className="flex items-start gap-2 text-sm" htmlFor="ack-discrepancies">
          <input
            id="ack-discrepancies"
            data-testid="acknowledge-discrepancies"
            type="checkbox"
            className="mt-1"
            checked={ack}
            onChange={(event) => setAck(event.target.checked)}
          />
          <span>Acknowledge discrepancies before accepting this delivery.</span>
        </label>
      ) : null}
      <label className="lbl" htmlFor="receipt-notes">
        Notes
        <textarea
          id="receipt-notes"
          data-testid="receipt-notes"
          className="field min-h-16 w-full"
          value={notes || ""}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>
      {canAccept ? (
        <button type="button" className="btn btn-primary w-full" data-testid="accept-delivery" disabled={busy} onClick={() => void accept()}>
          Accept Delivery
        </button>
      ) : null}
      {error ? (
        <p className="banner-error" role="alert" data-testid="receive-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
