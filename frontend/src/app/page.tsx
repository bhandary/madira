"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BriefingCards } from "@/components/BriefingCards";
import { SommelierChat } from "@/components/SommelierChat";
import { decideReminder, getTonight, getTonightBriefing, type TonightBoard, type TonightEnvelope } from "@/lib/api";

function boardFromEnvelope(envelope: TonightEnvelope): TonightBoard {
  return {
    service_date: envelope.service_date,
    briefing_hour: envelope.briefing_hour,
    timezone: envelope.timezone,
    available: envelope.available,
    role: envelope.role,
    briefing: envelope.briefing,
    low_stock: [],
    storage_alerts: [],
    deliveries_due: [],
    approvals: [],
    expiring_certificates: [],
    pos_alerts: [],
    sensors: [],
    reminders: [],
  };
}

export default function HomePage() {
  const [board, setBoard] = useState<TonightBoard | null>(null);
  const [partial, setPartial] = useState(false);
  const [error, setError] = useState("");
  const [reminderBusy, setReminderBusy] = useState("");

  useEffect(() => {
    let cancelled = false;
    const day = new URLSearchParams(window.location.search).get("day") || "";
    const load = day
      ? getTonightBriefing(day).then((envelope) => ({ board: boardFromEnvelope(envelope), partial: true }))
      : Promise.all([getTonight().catch(() => null), getTonightBriefing().catch(() => null)]).then(([live, cached]) => {
          if (live) return { board: live, partial: false };
          if (cached) return { board: boardFromEnvelope(cached), partial: true };
          throw new Error("Tonight did not load.");
        });
    load
      .then((payload) => {
        if (cancelled) return;
        setBoard(payload.board);
        setPartial(payload.partial);
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Tonight did not load.");
      });
    const onOffline = () => {
      if (cancelled) return;
      const day = new URLSearchParams(window.location.search).get("day") || "";
      setBoard(null);
      getTonightBriefing(day || undefined)
        .then((envelope) => {
          if (cancelled) return;
          setBoard(boardFromEnvelope(envelope));
          setPartial(true);
          setError("");
        })
        .catch((exc: unknown) => {
          if (!cancelled) setError(exc instanceof Error ? exc.message : "Tonight's briefing is not on this phone yet.");
        });
    };
    window.addEventListener("offline", onOffline);
    return () => {
      cancelled = true;
      window.removeEventListener("offline", onOffline);
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
        {partial ? (
          <p className="mt-2 text-sm text-[var(--muted)]">The rest of the board needs the network.</p>
        ) : board && board.low_stock.length ? (
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
      {partial ? null : (
      <section className="panel">
        <h2 className="text-base font-semibold">Storage alerts</h2>
        {board && board.storage_alerts.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.storage_alerts.map((row) => (
              <li key={row.id} data-testid="tonight-storage-alert" className="min-w-0 break-words">
                {row.zone} · {row.metric} · {row.status}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No open excursions.</p>
        )}
      </section>
      )}
      {partial ? null : (
      <section className="panel" data-testid="tonight-sensors">
        <h2 className="text-base font-semibold">Sensors</h2>
        {board && board.sensors && board.sensors.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.sensors.map((row) => (
              <li key={row.id} data-testid="tonight-sensor" className="min-w-0 break-words">
                {row.name} · {row.last_value || "no reading"}
                {row.stale ? ` · stale after ${row.stale_after_hours}h` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No sensors yet.</p>
        )}
      </section>
      )}
      {partial || (board?.role !== "Owner" && board?.role !== "Manager") ? null : (
      <section className="panel" data-testid="tonight-reminders">
        <h2 className="text-base font-semibold">Reminders</h2>
        {board && board.reminders && board.reminders.length ? (
          <ul className="mt-2 space-y-3 text-sm">
            {board.reminders.map((row) => (
              <li key={`${row.source_type}-${row.source_id}`} data-testid="tonight-reminder" className="min-w-0">
                <p className="break-words font-medium">{row.title}</p>
                <p className="break-words text-[var(--muted)]">{row.detail}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn min-h-11 whitespace-normal"
                    data-testid="reminder-ack"
                    disabled={reminderBusy === row.source_id}
                    onClick={() => {
                      setReminderBusy(row.source_id);
                      decideReminder({ source_type: row.source_type, source_id: row.source_id, action: "acknowledge" })
                        .then(() => getTonight())
                        .then((next) => setBoard(next))
                        .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : "The reminder could not be updated."))
                        .finally(() => setReminderBusy(""));
                    }}
                  >
                    Acknowledge
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary min-h-11 whitespace-normal"
                    data-testid="reminder-snooze"
                    disabled={reminderBusy === row.source_id}
                    onClick={() => {
                      setReminderBusy(row.source_id);
                      decideReminder({ source_type: row.source_type, source_id: row.source_id, action: "snooze", snooze_days: 7 })
                        .then(() => getTonight())
                        .then((next) => setBoard(next))
                        .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : "The reminder could not be updated."))
                        .finally(() => setReminderBusy(""));
                    }}
                  >
                    Snooze 7 days
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No reminders are due.</p>
        )}
      </section>
      )}
      {partial ? null : (
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
      )}
      {partial || (board?.role !== "Owner" && board?.role !== "Manager") ? null : (
      <section className="panel" data-testid="tonight-pos">
        <h2 className="text-base font-semibold">POS</h2>
        {board && board.pos_alerts && board.pos_alerts.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.pos_alerts.map((row) => (
              <li key={`${row.kind}-${row.title}`} data-testid="tonight-pos-alert">
                {row.href ? (
                  <a className="inline-flex min-h-11 items-center" href={row.href}>
                    {row.title}
                  </a>
                ) : (
                  row.title
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No POS gaps.</p>
        )}
      </section>
      )}
      {partial || (board?.role !== "Owner" && board?.role !== "Manager") ? null : (
      <section className="panel" data-testid="tonight-certificates">
        <h2 className="text-base font-semibold">Certificates</h2>
        {board && board.expiring_certificates.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.expiring_certificates.map((row) => (
              <li key={row.id} data-testid="tonight-certificate">
                {row.name} · {row.label} · {row.status_label}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No certificates are due.</p>
        )}
      </section>
      )}
      {partial ? null : (
      <section className="panel">
        <h2 className="text-base font-semibold">Approvals waiting</h2>
        {board && board.approvals.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {board.approvals.map((row) => (
              <li key={row.id} data-testid="tonight-approval">
                {row.href ? (
                  <a className="inline-flex min-h-11 items-center" href={row.href}>
                    {row.title}
                  </a>
                ) : (
                  row.title
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">Nothing is waiting on you.</p>
        )}
      </section>
      )}
      <SommelierChat />
    </div>
  );
}
