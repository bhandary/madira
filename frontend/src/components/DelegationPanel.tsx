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
    <aside
      className="rounded-2xl border border-gold/40 bg-white/70 p-4"
      data-testid="delegation-panel"
    >
      <p className="demo-ribbon text-[11px] text-burgundy">Head Sommelier · Deep Agents</p>
      <h2 className="mt-1 font-serif text-2xl">Delegation</h2>
      <p className="text-sm text-[#5c4c3c]">
        The orchestrator calls the <code>task</code> tool. Specialists run in isolation and return a single report.
      </p>
      {busy && <p className="mt-2 text-sm text-burgundy">Working…</p>}
      <ol className="mt-3 space-y-2">
        {rows.map((row) => (
          <li key={row.subagent} className="rounded-xl bg-cream px-3 py-2" data-testid={`delegate-${row.subagent}`}>
            <div className="flex items-center justify-between gap-2">
              <strong>{LABELS[row.subagent] || row.subagent}</strong>
              <span className="text-xs uppercase tracking-widest">{row.status}</span>
            </div>
            <p className="text-xs text-[#5c4c3c]">{row.description}</p>
          </li>
        ))}
        {!rows.length && <li className="text-sm text-[#7a6a58]">No specialists engaged yet.</li>}
      </ol>
      {todos.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm" data-testid="todo-list">
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
