"use client";

import type { AgentResult } from "@/lib/api";

const LABELS: Record<string, string> = {
  "menu-analyst": "Menu Analyst",
  "pairing-sommelier": "Pairing Sommelier",
  "list-curator": "List Curator",
  "inventory-purchasing": "Inventory & Purchasing",
  "staff-trainer": "Staff Trainer",
  "supplier-scheduler": "Supplier Scheduler",
};

export function DelegationPanel({ result, busy }: { result?: AgentResult | null; busy?: boolean }) {
  const rows = result?.delegation || [];
  const todos = result?.todos || [];
  return (
    <aside className="panel p-3" data-testid="delegation-panel">
      <p className="kicker">Head Sommelier · Deep Agents</p>
      <h2 className="mt-1 text-sm font-medium">Delegation</h2>
      <p className="mt-1 text-xs leading-5 text-muted">
        The orchestrator calls the <code>task</code> tool. Specialists run in isolation and return a single report.
      </p>
      {busy && (
        <p className="mt-2 text-xs text-wine" role="status">
          Working…
        </p>
      )}
      <ol className="mt-3 space-y-1.5">
        {rows.map((row) => (
          <li key={row.subagent} className="rounded-md bg-panel-2 px-2.5 py-2" data-testid={`delegate-${row.subagent}`}>
            <div className="flex items-center justify-between gap-2">
              <strong className="text-sm font-medium">{LABELS[row.subagent] || row.subagent}</strong>
              <span className="text-[10px] uppercase tracking-wider text-muted">{row.status}</span>
            </div>
            <p className="mt-0.5 text-xs text-muted">{row.description}</p>
          </li>
        ))}
        {!rows.length && <li className="text-sm text-muted">No specialists engaged yet.</li>}
      </ol>
      {todos.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-muted" data-testid="todo-list">
          {todos.map((todo, i) => (
            <li key={i}>
              [{todo.status}] {todo.content}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
