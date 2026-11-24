"use client";

import { FormEvent, useEffect, useState } from "react";
import { auditPackExportPath, previewAuditPack, type AuditPackPreview } from "@/lib/api";

function iso(offsetDays: number) {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + offsetDays);
  return day.toISOString().slice(0, 10);
}

function money(cents: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format((cents || 0) / 100);
}

export function AuditPackExport() {
  const [start, setStart] = useState(() => iso(-400));
  const [end, setEnd] = useState(() => iso(0));
  const [preview, setPreview] = useState<AuditPackPreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(startDate: string, endDate: string) {
    setBusy(true);
    setError("");
    try {
      setPreview(await previewAuditPack(startDate, endDate));
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "The audit pack could not be previewed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    previewAuditPack(start, end)
      .then((data) => {
        if (!cancelled) setPreview(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "The audit pack could not be previewed.");
      });
    return () => {
      cancelled = true;
    };
    // The first preview uses the default window. Later changes wait for Preview.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(start, end);
  }

  const queryStart = preview?.start_date || start;
  const queryEnd = preview?.end_date || end;
  const valuation = preview?.inventory_valuation;
  const invoices = preview?.invoice_register.length || 0;
  const gaps = preview?.missing_invoice_gaps.length || 0;

  return (
    <section className="mt-8 min-w-0" aria-labelledby="audit-pack-heading" data-testid="audit-pack">
      <h2 id="audit-pack-heading" className="text-lg font-medium">
        Audit pack
      </h2>
      <p className="mt-1 text-sm text-muted">
        A QBO/Xero journal, summaries, and a PDF for the selected dates. Records stay for the organization retention period, 7 years by default.
      </p>
      <form className="mt-3 grid gap-3" onSubmit={submit}>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="lbl min-w-0" htmlFor="audit-pack-start">
            Start
            <input
              id="audit-pack-start"
              data-testid="audit-pack-start"
              className="field w-full"
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              required
            />
          </label>
          <label className="lbl min-w-0" htmlFor="audit-pack-end">
            End
            <input
              id="audit-pack-end"
              data-testid="audit-pack-end"
              className="field w-full"
              type="date"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
              required
            />
          </label>
        </div>
        <button type="submit" className="btn btn-secondary w-full sm:w-auto" data-testid="audit-pack-preview" disabled={busy}>
          Preview audit pack
        </button>
      </form>
      {error ? (
        <p className="banner-error mt-3" role="alert" data-testid="audit-pack-error">
          {error}
        </p>
      ) : null}
      {preview && valuation ? (
        <div className="mt-3 grid gap-2">
          <article className="panel min-w-0 p-3" data-testid="audit-pack-valuation">
            <p className="kicker">Valuation</p>
            <p className="mt-1 break-words text-sm">
              {valuation.start_bottles} bottles · {money(valuation.start_value_cents)} → {valuation.end_bottles} bottles ·{" "}
              {money(valuation.end_value_cents)}
            </p>
          </article>
          <article className="panel min-w-0 p-3" data-testid="audit-pack-purchases">
            <p className="kicker">Purchases by supplier</p>
            <ul className="mt-1 space-y-1">
              {preview.purchases_by_supplier.map((row) => (
                <li key={row.supplier} className="break-words text-sm">
                  {row.supplier}: {row.po_count} POs · {row.invoice_count} invoices · {money(row.total_invoiced_cents)}
                </li>
              ))}
              {preview.purchases_by_supplier.length === 0 ? <li className="text-sm text-muted">No purchases in this window.</li> : null}
            </ul>
          </article>
          <article className="panel min-w-0 p-3" data-testid="audit-pack-invoices">
            <p className="kicker">Invoices</p>
            <p className="mt-1 text-sm">{invoices} in the register</p>
            <p className={gaps ? "mt-1 text-sm text-wine" : "mt-1 text-sm text-muted"} data-testid="audit-pack-gaps">
              {gaps ? `${gaps} missing invoice${gaps === 1 ? "" : "s"}` : "No missing invoices"}
            </p>
          </article>
          <article className="panel min-w-0 p-3" data-testid="audit-pack-variance">
            <p className="kicker">Variance and shrinkage</p>
            <p className="mt-1 text-sm">
              {preview.variance_and_shrinkage.quantity_delta} bottles · {money(preview.variance_and_shrinkage.cost_impact_cents)}
            </p>
          </article>
          <article className="panel min-w-0 p-3" data-testid="audit-pack-waste">
            <p className="kicker">Comps, breakage and waste</p>
            <p className="mt-1 text-sm">{money(preview.comp_breakage_waste.cost_impact_cents)}</p>
          </article>
          <article className="panel min-w-0 p-3" data-testid="audit-pack-retention">
            <p className="kicker">Retention</p>
            <p className="mt-1 break-words text-sm">
              {preview.retention.document_retention_years}-year retention · keep until {preview.retention.retain_until}
            </p>
          </article>
          <article className="panel min-w-0 p-3" data-testid="audit-pack-chain">
            <p className="kicker">Hash chain</p>
            <p className="mt-1 text-sm">{preview.chain.valid ? "Verified" : "Not verified"}</p>
          </article>
        </div>
      ) : busy ? (
        <p className="mt-3 text-sm text-muted">Loading the audit pack…</p>
      ) : null}
      <div className="mt-3 grid gap-2">
        <a className="btn btn-primary w-full" data-testid="download-audit-pack" href={auditPackExportPath(queryStart, queryEnd, "zip")}>
          Download Audit Pack (.zip)
        </a>
        <a className="btn btn-secondary w-full" data-testid="download-journal-csv" href={auditPackExportPath(queryStart, queryEnd, "journal_csv")}>
          Journal Entries CSV (QBO/Xero)
        </a>
        <a className="btn btn-secondary w-full" data-testid="download-summary-pdf" href={auditPackExportPath(queryStart, queryEnd, "summary_pdf")}>
          Summary PDF
        </a>
      </div>
    </section>
  );
}
