"use client";

import type { RepFollowupData, SourcingBriefData, TastingHistoryData } from "@/a2ui/sourcingSchema";

export function SourcingBriefView({ brief }: { brief: SourcingBriefData }) {
  return (
    <section className="space-y-3" data-testid="sourcing-brief">
      <h2 className="text-lg font-medium">{brief.title}</h2>
      {brief.items.length === 0 ? <p className="text-sm text-muted">The list covers every cell.</p> : null}
      <ul className="space-y-3">
        {brief.items.map((item) => (
          <li key={item.id} className="panel space-y-1 p-3" data-testid="want-item">
            <p className="text-sm font-medium">
              {item.category} · {item.style}
            </p>
            <p className="text-sm" data-testid="want-quantity">
              {item.price_band ? `${item.price_band} band · ` : ""}
              {item.quantity_hint} {item.quantity_hint === 1 ? "bottle" : "bottles"}
            </p>
            {item.dishes.length ? (
              <p className="text-sm text-muted">{item.dishes.map((dish) => dish.name).join(", ")}</p>
            ) : null}
            {item.rationale ? <p className="text-sm">{item.rationale}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RepFollowupView({ followup }: { followup: RepFollowupData }) {
  return (
    <section className="space-y-2" data-testid="rep-followup">
      <h2 className="text-lg font-medium">{followup.subject}</h2>
      <pre className="whitespace-pre-wrap text-sm">{followup.body}</pre>
      <p className="text-sm text-muted">{followup.sent ? "Sent" : "Draft only"}</p>
    </section>
  );
}

export function TastingHistoryView({ history }: { history: TastingHistoryData }) {
  return (
    <section className="space-y-3" data-testid="tasting-history">
      <h2 className="text-lg font-medium">Tasted and bought</h2>
      {history.rows.length === 0 ? <p className="text-sm text-muted">No tasting history yet.</p> : null}
      <ul className="space-y-2">
        {history.rows.map((row) => (
          <li key={`${row.supplier_id}:${row.product_id}`} className="panel p-3 text-sm" data-testid="history-row">
            <p className="font-medium">{row.product || "Unmatched sample"}</p>
            <p className="text-muted">{row.supplier || "No supplier"}</p>
            <p>
              Tasted {row.tasted} · Bought {row.bought_bottles} · Invoiced {row.invoiced_bottles}
            </p>
            {row.last_cost_label ? <p>Last cost {row.last_cost_label}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
