"use client";

import { coverageCell, type CoverageCell } from "@/a2ui/coverageGridSchema";

function asCells(value: unknown): CoverageCell[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((row) => {
    const parsed = coverageCell.safeParse(row);
    return parsed.success ? [parsed.data] : [];
  });
}

export function CoverageGrid({ cells }: { cells: unknown }) {
  const rows = asCells(cells);
  const categories = [...new Set(rows.map((row) => row.category))];
  return (
    <div className="min-w-0" data-testid="coverage-grid">
      <h3 className="text-base text-ink">Coverage</h3>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">No coverage cells yet.</p>
      ) : (
        <div className="mt-3 grid gap-3">
          {categories.map((category) => (
            <section key={category} className="panel p-3">
              <div className="kicker">{category}</div>
              <ul className="mt-2 grid gap-2">
                {rows
                  .filter((row) => row.category === category)
                  .map((row) => (
                    <li
                      key={`${row.category}-${row.style}-${row.band}-${row.dish_id || "house"}`}
                      className="flex min-h-11 items-center justify-between gap-3 text-sm"
                      data-testid="coverage-cell"
                      data-status={row.status}
                    >
                      <span className="min-w-0">
                        <span className="text-ink">{row.style}</span>
                        <span className="text-muted"> · {row.band}</span>
                        <span className="block truncate text-xs text-muted">{row.name}</span>
                      </span>
                      <span className={row.status === "filled" ? "badge badge-ok" : "badge badge-draft"}>
                        {row.status === "filled" ? "On list" : "Buy"}
                      </span>
                    </li>
                  ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
