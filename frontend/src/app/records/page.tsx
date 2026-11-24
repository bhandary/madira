"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { AuditTable, ChainBadge } from "@/components/AuditTable";
import {
  ApiError,
  getAuditEvents,
  getRetention,
  listDocuments,
  updateRetention,
  uploadDocument,
  type AuditChain,
  type AuditEventRow,
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
