"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BriefingCards } from "@/components/BriefingCards";
import { SommelierChat } from "@/components/SommelierChat";
import { getTonight, type TonightBoard } from "@/lib/api";

export default function HomePage() {
  const [board, setBoard] = useState<TonightBoard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getTonight()
      .then((payload) => {
        if (!cancelled) setBoard(payload);
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Tonight did not load.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="h-page">Tonight</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">The floor, before service.</p>
        </div>
        <Link href="/lookup" className="btn btn-secondary" data-testid="lookup-link">
          Lookup
        </Link>
      </header>
      {error ? (
        <p className="text-sm" role="alert">
          {error}
        </p>
      ) : null}
      {board?.briefing ? (
        <BriefingCards briefing={board.briefing} />
      ) : board ? (
        <p className="text-sm text-[var(--muted)]">The briefing opens at {board.briefing_hour}:00.</p>
      ) : null}
      <section className="panel">
        <h2 className="text-base font-semibold">Low stock</h2>
        {board && board.low_stock.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.low_stock.map((row) => (
              <li key={row.sku}>
                {row.name} · {row.on_hand} / par {row.par}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">Nothing is under par.</p>
        )}
      </section>
      <section className="panel">
        <h2 className="text-base font-semibold">Storage alerts</h2>
        {board && board.storage_alerts.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.storage_alerts.map((row) => (
              <li key={row.id}>
                {row.zone} · {row.metric} · {row.status}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No open excursions.</p>
        )}
      </section>
      <section className="panel">
        <h2 className="text-base font-semibold">Deliveries due</h2>
        {board && board.deliveries_due.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.deliveries_due.map((row) => (
              <li key={row.po_number}>
                {row.po_number} · {row.supplier} · {row.expected_delivery_date || "unscheduled"}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No deliveries are due.</p>
        )}
      </section>
      <section className="panel">
        <h2 className="text-base font-semibold">Approvals waiting</h2>
        {board && board.approvals.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.approvals.map((row) => (
              <li key={row.id}>
                {row.title}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">Nothing is waiting on you.</p>
        )}
      </section>
      <SommelierChat />
    </div>
  );
}
