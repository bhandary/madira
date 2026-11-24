"use client";

import type { LookupHit } from "@/lib/api";

export function FloorLookup({ results }: { results: LookupHit[] }) {
  if (!results.length) {
    return <p className="text-sm text-[var(--muted)]">Nothing on the floor matches that.</p>;
  }
  return (
    <ul className="space-y-3">
      {results.map((hit) => (
        <li key={`${hit.name}-${hit.price_cents}`} className="panel" data-testid="lookup-result">
          <h2 className="text-base font-semibold">{hit.name}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {[hit.producer, hit.grape, hit.region].filter(Boolean).join(" · ")}
          </p>
          <p className="mt-2 text-sm" data-testid="lookup-flavor">
            {hit.flavor_profile}
          </p>
          {hit.pairing ? <p className="mt-2 text-sm">Pairs with {hit.pairing}.</p> : null}
          <p className="mt-2 text-sm" data-testid="lookup-script">
            {hit.server_script}
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-[var(--muted)]">Glass</dt>
              <dd data-testid="lookup-glassware">{hit.glassware || "—"}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Temperature</dt>
              <dd data-testid="lookup-temperature">{hit.serving_temperature || "—"}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Pour</dt>
              <dd data-testid="lookup-pour">{hit.pour_size || "—"}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Stock</dt>
              <dd data-testid="lookup-stock">{hit.stock}</dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  );
}
