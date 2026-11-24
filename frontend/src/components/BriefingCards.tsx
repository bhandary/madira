"use client";

import { useEffect, useRef, useState } from "react";
import type { BriefingPayload } from "@/a2ui/briefingCardsSchema";
import { acknowledgeBriefing } from "@/lib/api";

export function BriefingCards({ briefing }: { briefing: BriefingPayload }) {
  const started = useRef(0);
  useEffect(() => {
    started.current = Date.now();
  }, []);
  const originX = useRef<number | null>(null);
  const cards = [{ kind: "intro", title: "Tonight", body: briefing.intro, items: [] }, ...briefing.cards];
  const [index, setIndex] = useState(0);
  const [acknowledged, setAcknowledged] = useState(briefing.acknowledged);
  const [seconds, setSeconds] = useState<number | null>(briefing.seconds_to_ack);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const card = cards[Math.min(index, cards.length - 1)];
  const last = index >= cards.length - 1;

  function advance() {
    setIndex((current) => Math.min(current + 1, cards.length - 1));
  }

  async function ack() {
    if (!briefing.id || acknowledged || busy) return;
    setBusy(true);
    setError("");
    const elapsed = Math.max(0, Math.min(86400, Math.round((Date.now() - started.current) / 1000)));
    try {
      const body = await acknowledgeBriefing(briefing.id, elapsed);
      setAcknowledged(true);
      setSeconds(body.seconds_to_ack);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The acknowledgement did not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="panel"
      data-testid="briefing-stack"
      onPointerDown={(event) => {
        originX.current = event.clientX;
      }}
      onPointerUp={(event) => {
        if (originX.current !== null && originX.current - event.clientX > 40) advance();
        originX.current = null;
      }}
    >
      <article className="rounded-md border border-[var(--line)] p-4" data-testid="briefing-card" data-kind={card.kind}>
        <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
          {index + 1} of {cards.length}
        </p>
        <h2 className="mt-2 text-lg font-semibold">{card.title}</h2>
        {card.body ? <p className="mt-2 text-sm leading-6">{card.body}</p> : null}
        {card.items.length ? (
          <ul className="mt-3 space-y-2">
            {card.items.map((item) => (
              <li key={`${card.kind}-${item.title}`}>
                <p className="text-sm font-medium">{item.title}</p>
                {item.detail ? <p className="text-sm text-[var(--muted)]">{item.detail}</p> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </article>
      <div className="mt-3 flex flex-col gap-2">
        {last ? (
          acknowledged ? (
            <p className="text-sm" data-testid="briefing-acked">
              Acknowledged{seconds === null ? "" : ` in ${seconds}s`}.
            </p>
          ) : (
            <button type="button" className="btn btn-primary w-full" data-testid="briefing-ack" disabled={briefing.status !== "published" || busy} onClick={ack}>
              Acknowledge
            </button>
          )
        ) : (
          <button type="button" className="btn btn-secondary w-full" data-testid="briefing-next" onClick={advance}>
            Next card
          </button>
        )}
        {error ? (
          <p className="text-sm" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
