"use client";

import type { AuditorTableData } from "@/a2ui/auditorTableSchema";

function money(cents: number) {
  return (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function cellText(value: string | number, type: string) {
  if (type === "money" && typeof value === "number") return money(value);
  return String(value);
}

function safeHref(href: string) {
  if (!href.startsWith("/") || href.startsWith("//")) return "";
  return href;
}

export function AuditorTableView({ table }: { table: AuditorTableData }) {
  const types = Object.fromEntries(table.columns.map((column) => [column.key, column.type]));
  return (
    <div data-testid="auditor-table" className="min-w-0">
      <p className="break-words text-sm text-muted" data-testid="auditor-totals">
        {Object.entries(table.totals)
          .map(([key, value]) => `${key} ${value}`)
          .join(" · ")}
        {` · ${table.page.total} in the filter`}
      </p>
      <div className="table-wrap mt-3">
        <table>
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {table.rows.length === 0 ? (
              <tr>
                <td colSpan={table.columns.length + 1}>Nothing matches this filter.</td>
              </tr>
            ) : (
              table.rows.map((row) => (
                <tr key={row.id} data-testid="auditor-row">
                  {table.columns.map((column) => (
                    <td key={column.key} className="whitespace-nowrap">
                      {cellText(row.cells[column.key] ?? "", types[column.key] || "text")}
                    </td>
                  ))}
                  <td>
                    <span className="flex flex-wrap gap-2">
                      {row.links.map((link) => {
                        const href = safeHref(link.href);
                        if (!href) return null;
                        return (
                          <a key={href} href={href} data-testid="auditor-link" className="underline">
                            {link.label}
                          </a>
                        );
                      })}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
