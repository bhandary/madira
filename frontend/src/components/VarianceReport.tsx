"use client";

import { useState } from "react";
import { formatCount } from "@/components/CountSheet";

export type VarianceLine = {
  sku: string;
  name: string;
  counted_quantity: number | null;
  expected_quantity: number;
  variance: number | null;
  variance_value_cents: number | null;
  unit_cost_cents: number;
};

export type ConflictReading = {
  device_id: string;
  counted_quantity: number;
  counted_at?: string | null;
};

export type CountConflict = {
  sku: string;
  readings: ConflictReading[];
  resolved: boolean;
  resolved_quantity: number | null;
};

export type VarianceReportData = {
  session: { id: string; status: string; location_name?: string };
  lines: VarianceLine[];
  conflicts: CountConflict[];
};

function money(cents: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format((cents || 0) / 100);
}

function asReport(value: unknown): VarianceReportData | null {
  if (!value || typeof value !== "object") return null;
  const row = value as VarianceReportData;
  if (!row.session || !Array.isArray(row.lines)) return null;
  return {
    session: row.session,
    lines: row.lines,
    conflicts: Array.isArray(row.conflicts) ? row.conflicts : [],
  };
}

function ConflictCard({
  conflict,
  busy,
  onResolve,
}: {
  conflict: CountConflict;
  busy?: boolean;
  onResolve?: (sku: string, quantity: number) => void;
}) {
  const [quantity, setQuantity] = useState(
    conflict.resolved_quantity == null ? "" : formatCount(Number(conflict.resolved_quantity)),
  );
  return (
    <article className="panel p-3" data-testid="count-conflict" data-sku={conflict.sku}>
      <h3 className="text-sm font-medium">{conflict.sku}</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {conflict.readings.map((reading) => (
          <li key={reading.device_id}>
            {reading.device_id}: {formatCount(Number(reading.counted_quantity))}
          </li>
        ))}
      </ul>
      {conflict.resolved ? (
        <p className="mt-2 text-sm">Resolved at {formatCount(Number(conflict.resolved_quantity))}</p>
      ) : onResolve ? (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="lbl min-w-0 flex-1" htmlFor={`resolve-${conflict.sku}`}>
            Resolved quantity
            <input
              id={`resolve-${conflict.sku}`}
              data-testid="conflict-qty"
              className="field"
              inputMode="decimal"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            data-testid="conflict-resolve"
            disabled={busy}
            onClick={() => {
              const next = Number(quantity);
              if (!Number.isFinite(next) || next < 0) return;
              onResolve(conflict.sku, next);
            }}
          >
            Resolve
          </button>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted">Needs a resolved quantity.</p>
      )}
    </article>
  );
}

export function VarianceReport({
  report,
  onResolve,
  onApprove,
  busy,
}: {
  report?: unknown;
  onResolve?: (sku: string, quantity: number) => void;
  onApprove?: () => void;
  busy?: boolean;
}) {
  const current = asReport(report);
  if (!current) return null;
  const open = current.conflicts.filter((conflict) => !conflict.resolved);
  const approved = current.session.status === "approved";
  return (
    <section className="space-y-3" data-testid="variance-report" aria-label="Variance report">
      <div>
        <h2 className="text-base font-medium">Variance review</h2>
        <p className="text-sm text-muted">{current.session.location_name || "Location"} · {current.session.status.replace(/_/g, " ")}</p>
      </div>
      {current.lines.length === 0 ? <p className="text-sm text-muted">No counted SKUs.</p> : null}
      <ul className="space-y-2">
        {current.lines.map((line) => (
          <li key={line.sku} className="panel p-3" data-testid="variance-line" data-sku={line.sku}>
            <div className="font-mono text-xs">{line.sku}</div>
            <div className="text-sm">{line.name}</div>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-muted">Expected</dt>
                <dd>{formatCount(Number(line.expected_quantity))}</dd>
              </div>
              <div>
                <dt className="text-muted">Counted</dt>
                <dd>{line.counted_quantity == null ? "—" : formatCount(Number(line.counted_quantity))}</dd>
              </div>
              <div>
                <dt className="text-muted">Delta</dt>
                <dd>{line.variance == null ? "—" : formatCount(Number(line.variance))}</dd>
              </div>
              <div>
                <dt className="text-muted">Dollar impact</dt>
                <dd>{line.variance_value_cents == null ? "—" : money(line.variance_value_cents)}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
      {current.conflicts.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Device conflicts</h3>
          {current.conflicts.map((conflict) => (
            <ConflictCard key={conflict.sku} conflict={conflict} busy={busy} onResolve={onResolve} />
          ))}
        </div>
      ) : null}
      {approved ? (
        <p className="text-sm" data-testid="count-approved">
          Adjustments posted.
        </p>
      ) : onApprove ? (
        <button
          type="button"
          className="btn btn-primary w-full"
          data-testid="count-approve"
          disabled={busy || open.length > 0}
          onClick={onApprove}
        >
          Approve & post adjustments
        </button>
      ) : null}
    </section>
  );
}
