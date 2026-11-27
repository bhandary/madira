"use client";

import { useEffect, useState } from "react";
import { auditorTable, type AuditorTableData } from "@/a2ui/auditorTableSchema";
import { AuditorTableView } from "@/components/AuditorTable";
import { ApiError, getAuditQuery } from "@/lib/api";

const QUERIES = [
  { id: "stock", label: "Stock and depletion" },
  { id: "conditions", label: "Excursions and sensors" },
  { id: "compliance", label: "Licenses and reminders" },
  { id: "pos", label: "POS gaps" },
  { id: "lists", label: "List versions" },
  { id: "purchases", label: "Purchases and receipts" },
  { id: "events", label: "Audit events" },
];

export default function AuditPage() {
  const [kind, setKind] = useState("stock");
  const [offset, setOffset] = useState(0);
  const [table, setTable] = useState<AuditorTableData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAuditQuery(kind, offset)
      .then((payload) => {
        if (cancelled) return;
        const parsed = auditorTable.safeParse(payload.audit_table);
        if (!parsed.success) {
          setError("The audit table could not be read.");
          setTable(null);
          return;
        }
        setTable(parsed.data);
        setError("");
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof ApiError ? exc.message : "The audit table could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [kind, offset]);

  const page = table?.page;

  return (
    <main className="mx-auto w-full max-w-lg px-4 py-6">
      <h1 className="text-2xl font-semibold">Audit</h1>
      <p className="mt-1 text-sm text-muted">Read-only tables. Totals and links come from the records.</p>
      <label className="mt-4 block text-sm" htmlFor="audit-kind">
        Query
        <select
          id="audit-kind"
          data-testid="audit-kind"
          className="mt-1 min-h-11 w-full"
          value={kind}
          onChange={(event) => {
            setKind(event.target.value);
            setOffset(0);
          }}
        >
          {QUERIES.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {error ? <p className="mt-3 text-sm text-alert">{error}</p> : null}
      {table ? (
        <div className="mt-4">
          <AuditorTableView table={table} />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className="min-h-11 flex-1 whitespace-normal"
              disabled={!page || page.offset <= 0}
              onClick={() => setOffset(Math.max(0, (page?.offset || 0) - (page?.limit || 25)))}
            >
              Previous
            </button>
            <button
              type="button"
              className="min-h-11 flex-1 whitespace-normal"
              disabled={!page || page.offset + page.limit >= page.total}
              onClick={() => setOffset((page?.offset || 0) + (page?.limit || 25))}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </main>
  );
}
