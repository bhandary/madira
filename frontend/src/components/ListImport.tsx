"use client";

import { useState } from "react";
import { ApiError, importList, type ListImportResult, type ListImportRow } from "@/lib/api";

function money(minor: number, currency: string) {
  const code = /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  return (minor / 100).toLocaleString(undefined, {
    style: "currency",
    currency: code,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function statusLabel(row: ListImportRow) {
  if (row.status === "match") return "Matched";
  if (row.status === "error") return "Error";
  if (row.action === "new_variant") return "New variant";
  return "New product";
}

function statusTone(row: ListImportRow) {
  if (row.status === "match") return "badge badge-ok";
  if (row.status === "error") return "badge badge-alert";
  return "badge badge-draft";
}

export function ListImport() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ListImportResult | null>(null);
  const [imported, setImported] = useState<ListImportResult["list"] | null>(null);
  const [busy, setBusy] = useState<"preview" | "confirm" | null>(null);
  const [error, setError] = useState("");

  const importable = preview ? preview.matched + preview.new : 0;

  async function run(confirm: boolean) {
    if (!file || busy) return;
    setBusy(confirm ? "confirm" : "preview");
    setError("");
    try {
      const result = await importList(file, confirm);
      if (confirm) {
        setImported(result.list ?? null);
        setPreview(result);
      } else {
        setPreview(result);
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "The list could not be imported.";
      setError(message || "The list could not be imported.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel mt-5 min-w-0 p-4" data-testid="list-import">
      <h2 className="text-lg text-ink">Import CSV</h2>
      <p className="mt-1 text-sm text-muted">
        Upload a beverage list. Preview matches, new bottles, and row errors, then confirm.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="lbl min-w-0 flex-1" htmlFor="list-import-file">
          CSV file
          <input
            id="list-import-file"
            data-testid="list-import-file"
            type="file"
            accept=".csv,text/csv"
            className="field-file"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPreview(null);
              setError("");
            }}
          />
        </label>
        <button
          type="button"
          className="btn btn-secondary"
          data-testid="list-import-preview"
          disabled={!file || busy !== null}
          onClick={() => void run(false)}
        >
          {busy === "preview" ? "Previewing…" : "Preview"}
        </button>
      </div>
      {error && (
        <p className="banner-error mt-3" role="alert" data-testid="list-import-error">
          {error}
        </p>
      )}
      {preview && (
        <div className="mt-4 min-w-0">
          <p className="text-sm text-ink" data-testid="list-import-summary">
            {preview.matched} matched · {preview.new_products} new products · {preview.new_variants} new variants ·{" "}
            {preview.errors} errors
          </p>
          <div className="table-wrap mt-3">
            <table data-testid="list-import-preview-table">
              <thead>
                <tr>
                  {["Line", "Status", "Section", "Name", "Detail"].map((heading) => (
                    <th key={heading}>{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.line} data-testid="list-import-row">
                    <td>{row.line}</td>
                    <td>
                      <span className={statusTone(row)}>{statusLabel(row)}</span>
                    </td>
                    <td>{row.section || "—"}</td>
                    <td>
                      {row.name || "—"}
                      {row.producer ? <div className="text-xs text-muted">{row.producer}</div> : null}
                    </td>
                    <td>{row.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="btn btn-primary mt-3"
            data-testid="list-import-confirm"
            disabled={preview.mode === "confirmed" || importable === 0 || busy !== null}
            onClick={() => void run(true)}
          >
            {busy === "confirm" ? "Importing…" : "Confirm import"}
          </button>
        </div>
      )}
      {imported && (
        <div className="mt-5 min-w-0">
          <h3 className="text-base text-ink" data-testid="list-import-name">
            {imported.name}
          </h3>
          <div className="table-wrap mt-3" data-testid="list-import-entries">
            <table>
              <thead>
                <tr>
                  {["Section", "Name", "Vintage", "Glass", "Bottle"].map((heading) => (
                    <th key={heading}>{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {imported.items.map((item, index) => (
                  <tr key={`${item.name}-${index}`} data-testid="list-import-entry">
                    <td>{item.section || "—"}</td>
                    <td>
                      {item.name}
                      {item.producer ? <div className="text-xs text-muted">{item.producer}</div> : null}
                    </td>
                    <td>{item.vintage || "—"}</td>
                    <td>{item.pour_price ? money(item.pour_price, imported.currency) : "—"}</td>
                    <td>{item.bottle_price ? money(item.bottle_price, imported.currency) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
