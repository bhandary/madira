"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { AuditPackExport } from "@/components/AuditPackExport";
import { AuditTable, ChainBadge } from "@/components/AuditTable";
import {
  ApiError,
  getAuditEvents,
  getBriefingReport,
  getRetention,
  listDocuments,
  updateRetention,
  uploadDocument,
  type AuditChain,
  type AuditEventRow,
  type BriefingReport,
  type VaultDocument,
} from "@/lib/api";

const DOC_TYPES = [
  ["invoice", "Invoice"],
  ["po_pdf", "Purchase order PDF"],
  ["purchase_order", "Purchase order"],
  ["delivery_note", "Delivery note"],
  ["license", "License"],
  ["certificate", "Certificate"],
  ["other", "Other"],
] as const;

function isoDate(offsetDays: number) {
  const now = new Date();
  const day = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + offsetDays));
  return day.toISOString().slice(0, 10);
}

function completionRows(report: BriefingReport) {
  const people = new Map<string, { id: string; name: string; acked: number; total: number }>();
  for (const day of report.days) {
    if (!day.briefing_id || day.status !== "published") continue;
    for (const user of day.users) {
      const row = people.get(user.user_id) || { id: user.user_id, name: user.name || "Unnamed", acked: 0, total: 0 };
      row.total += 1;
      if (user.acknowledged) row.acked += 1;
      people.set(user.user_id, row);
    }
  }
  return [...people.values()].sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

function bytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function RecordsPage() {
  const [events, setEvents] = useState<AuditEventRow[]>([]);
  const [chain, setChain] = useState<AuditChain | null>(null);
  const [documents, setDocuments] = useState<VaultDocument[]>([]);
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");
  const [docType, setDocType] = useState<string>("license");
  const [file, setFile] = useState<File | null>(null);
  const [years, setYears] = useState("7");
  const [canEdit, setCanEdit] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [reportStart, setReportStart] = useState(() => isoDate(-6));
  const [reportEnd, setReportEnd] = useState(() => isoDate(0));
  const [report, setReport] = useState<BriefingReport | null>(null);

  const refresh = useCallback(async (filters?: { entityType?: string; action?: string }) => {
    const [ledger, vault, retention] = await Promise.all([
      getAuditEvents({
        entity_type: filters?.entityType ?? "",
        action: filters?.action ?? "",
      }),
      listDocuments(),
      getRetention(),
    ]);
    setEvents(ledger.events);
    setChain(ledger.chain);
    setDocuments(vault.documents);
    setYears(String(retention.document_retention_years));
    setCanEdit(retention.can_edit);
    setLoaded(true);
    setError("");
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getAuditEvents(), listDocuments(), getRetention()])
      .then(([ledger, vault, retention]) => {
        if (cancelled) return;
        setEvents(ledger.events);
        setChain(ledger.chain);
        setDocuments(vault.documents);
        setYears(String(retention.document_retention_years));
        setCanEdit(retention.can_edit);
        setLoaded(true);
        setError("");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoaded(true);
        setError(err instanceof Error ? err.message : "Records could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function applyFilters(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await refresh({ entityType, action });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The ledger could not be filtered.");
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await uploadDocument({ file, doc_type: docType });
      setFile(null);
      await refresh({ entityType, action });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function saveRetention(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await updateRetention(Number(years));
      setYears(String(next.document_retention_years));
      setCanEdit(next.can_edit);
      await refresh({ entityType, action });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retention could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function loadReport(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setReport(await getBriefingReport(reportStart, reportEnd));
    } catch (err) {
      setReport(null);
      setError(err instanceof Error ? err.message : "The briefing report could not be loaded.");
    } finally {
      setBusy(false);
    }
  }

  const completions = report ? completionRows(report) : [];

  return (
    <div className="min-w-0" data-testid="records-page">
      <h1 className="h-page">Records</h1>
      <p className="lead">
        The audit ledger is append-only and hash-chained. Invoices, licenses, and certificates stay in the document vault.
      </p>
      {error ? (
        <p className="banner-error mt-4" role="alert" data-testid="records-error">
          {error}
        </p>
      ) : null}

      <section className="mt-6" aria-labelledby="briefing-report-heading" data-testid="briefing-report">
        <h2 id="briefing-report-heading" className="text-lg font-medium">
          Briefing completion
        </h2>
        <p className="mt-1 text-sm text-muted">Published briefings in the range, and who acknowledged them.</p>
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={loadReport}>
          <label className="lbl" htmlFor="briefing-report-start">
            From
            <input
              id="briefing-report-start"
              data-testid="briefing-report-start"
              className="field min-h-11 w-40"
              type="date"
              value={reportStart}
              onChange={(event) => setReportStart(event.target.value)}
            />
          </label>
          <label className="lbl" htmlFor="briefing-report-end">
            To
            <input
              id="briefing-report-end"
              data-testid="briefing-report-end"
              className="field min-h-11 w-40"
              type="date"
              value={reportEnd}
              onChange={(event) => setReportEnd(event.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-secondary min-h-11" data-testid="briefing-report-load" disabled={busy}>
            Show completion
          </button>
        </form>
        {report ? (
          <ul className="mt-3 space-y-2">
            {completions.map((row) => (
              <li key={row.id} className="panel flex min-h-11 items-center justify-between gap-3 px-3 text-sm" data-testid="briefing-report-person">
                <span>{row.name}</span>
                <span>
                  {row.acked}/{row.total}
                </span>
              </li>
            ))}
            {completions.length === 0 ? <li className="text-sm text-muted">No published briefings in that range.</li> : null}
          </ul>
        ) : null}
      </section>

      <section className="mt-6" aria-labelledby="audit-heading">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="audit-heading" className="text-lg font-medium">
            Audit ledger
          </h2>
          {chain ? <ChainBadge chain={chain} /> : null}
        </div>
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={applyFilters}>
          <label className="lbl" htmlFor="audit-entity">
            Entity
            <input
              id="audit-entity"
              data-testid="audit-entity"
              className="field w-40"
              value={entityType}
              onChange={(event) => setEntityType(event.target.value)}
              placeholder="document"
            />
          </label>
          <label className="lbl" htmlFor="audit-action">
            Action
            <input
              id="audit-action"
              data-testid="audit-action"
              className="field w-48"
              value={action}
              onChange={(event) => setAction(event.target.value)}
              placeholder="document.store"
            />
          </label>
          <button type="submit" className="btn btn-secondary" data-testid="audit-filter" disabled={busy}>
            Filter
          </button>
        </form>
        <div className="mt-3">
          {loaded ? (
            <AuditTable events={events} />
          ) : (
            <p className="text-sm text-muted">Loading the ledger…</p>
          )}
        </div>
      </section>

      <section className="mt-8" aria-labelledby="vault-heading">
        <h2 id="vault-heading" className="text-lg font-medium">
          Document vault
        </h2>
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={upload}>
          <label className="lbl" htmlFor="vault-doc-type">
            Type
            <select
              id="vault-doc-type"
              data-testid="vault-doc-type"
              className="field w-52"
              value={docType}
              onChange={(event) => setDocType(event.target.value)}
            >
              {DOC_TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="lbl" htmlFor="vault-file">
            File
            <input
              id="vault-file"
              data-testid="vault-file"
              className="field-file w-64 max-w-full"
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp,.csv,.txt,application/pdf,image/png,image/jpeg,image/webp,text/csv,text/plain"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <button type="submit" className="btn btn-primary" data-testid="vault-upload" disabled={busy}>
            Upload document
          </button>
        </form>
        <ul className="mt-4 space-y-2" data-testid="document-list">
          {documents.map((doc) => (
            <li key={doc.id} className="panel p-3" data-testid="document-row">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium">{doc.filename}</div>
                  <div className="mt-1 text-xs text-muted">
                    {doc.doc_type} · <span data-testid="document-size">{bytes(doc.size_bytes)}</span>
                    {" · "}
                    <span className="font-mono" data-testid="document-sha" data-sha={doc.sha256} title={doc.sha256}>
                      {doc.sha256.slice(0, 12)}
                    </span>
                  </div>
                </div>
                <a
                  className="btn btn-secondary"
                  data-testid="document-download"
                  href={`/madira-api/compliance/documents/${doc.id}/download`}
                >
                  Download
                </a>
              </div>
            </li>
          ))}
          {loaded && documents.length === 0 ? <li className="text-sm text-muted">No documents filed yet.</li> : null}
        </ul>
      </section>

      <AuditPackExport />

      <section className="mt-8" aria-labelledby="retention-heading">
        <h2 id="retention-heading" className="text-lg font-medium">
          Retention
        </h2>
        <p className="mt-1 text-sm text-muted">
          The organization default is 7 years. An Owner can set a whole number of years from 1 to 25.
        </p>
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={saveRetention}>
          <label className="lbl" htmlFor="retention-years">
            Years
            <input
              id="retention-years"
              data-testid="retention-years"
              className="field w-28"
              type="number"
              min={1}
              max={25}
              step={1}
              value={years}
              disabled={!canEdit}
              onChange={(event) => setYears(event.target.value)}
            />
          </label>
          {canEdit ? (
            <button type="submit" className="btn btn-secondary" data-testid="retention-save" disabled={busy}>
              Save retention
            </button>
          ) : (
            <p className="text-sm text-muted">Only an Owner can change retention.</p>
          )}
        </form>
      </section>
    </div>
  );
}
