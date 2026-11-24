"use client";

export type CountSessionView = {
  id: string;
  status: string;
  location_id?: string;
  location_name?: string;
  notes?: string;
};

export type CountLineView = {
  id: string;
  sku: string;
  name: string;
  counted_quantity: number;
  expected_quantity?: number | null;
  device_id: string;
  bin_code?: string;
  counted_at?: string | null;
};

function asSession(value: unknown): CountSessionView | null {
  if (!value || typeof value !== "object") return null;
  const row = value as CountSessionView;
  if (!row.id || !row.status) return null;
  return row;
}

function asLines(value: unknown): CountLineView[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row) => row && typeof row === "object" && typeof row.sku === "string") as CountLineView[];
}

export function formatCount(value: number) {
  if (!Number.isFinite(value)) return "0";
  const rounded = Math.round(value * 100) / 100;
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toFixed(2).replace(/0$/, "");
}

export function CountSheet({ session, lines }: { session?: unknown; lines?: unknown }) {
  const current = asSession(session);
  const list = asLines(lines);
  return (
    <section className="space-y-2" data-testid="count-sheet" aria-label="Count sheet">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-medium">{current?.location_name || "Count"}</h2>
        <span className="text-sm text-muted">{current?.status?.replace(/_/g, " ") || "In progress"}</span>
      </div>
      {list.length === 0 ? (
        <p className="text-sm text-muted">No bottles counted yet.</p>
      ) : (
        <ul className="space-y-2">
          {list.map((line) => (
            <li key={line.id || `${line.sku}-${line.device_id}-${line.counted_at}`} className="panel p-3" data-testid="count-line">
              <div className="flex items-baseline justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs">{line.sku}</div>
                  <div className="truncate text-sm">{line.name}</div>
                </div>
                <div className="text-lg tabular-nums">{formatCount(Number(line.counted_quantity))}</div>
              </div>
              <p className="mt-1 text-xs text-muted">
                {line.device_id}
                {line.bin_code ? ` · ${line.bin_code}` : ""}
                {line.expected_quantity == null ? "" : ` · expected ${formatCount(Number(line.expected_quantity))}`}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
