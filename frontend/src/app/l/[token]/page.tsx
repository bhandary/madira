"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, getPublicList, type PublicList } from "@/lib/api";

function money(minor: number, currency: string) {
  const code = /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  return (minor / 100).toLocaleString(undefined, { style: "currency", currency: code });
}

export default function PublicListPage() {
  const params = useParams<{ token: string }>();
  const token = typeof params.token === "string" ? params.token : "";
  const [list, setList] = useState<PublicList | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!token) return;
    let live = true;
    getPublicList(token)
      .then((body) => {
        if (!live) return;
        setList(body);
        setMissing(false);
      })
      .catch((exc) => {
        if (!live) return;
        setList(null);
        setMissing(true);
        if (!(exc instanceof ApiError)) setMissing(true);
      });
    return () => {
      live = false;
    };
  }, [token]);

  useEffect(() => {
    if (!list) return;
    const previous = document.title;
    document.title = list.list.list_name || list.venue_name;
    return () => {
      document.title = previous;
    };
  }, [list]);

  if (missing) {
    return (
      <main className="public-list min-h-dvh bg-canvas px-4 py-8 text-ink">
        <p className="text-base" data-testid="public-missing">
          This list is not available.
        </p>
      </main>
    );
  }

  if (!list) {
    return (
      <main className="public-list min-h-dvh bg-canvas px-4 py-8 text-ink">
        <p className="text-base text-muted">Loading the list.</p>
      </main>
    );
  }

  return (
    <main className="public-list min-h-dvh bg-canvas px-4 py-6 text-ink" data-testid="public-list">
      <p className="text-sm text-muted" data-testid="public-venue">
        {list.venue_name}
      </p>
      <h1 className="mt-1 text-2xl">{list.list.list_name}</h1>
      {list.list.sections.map((section) => (
        <section key={section.name} className="mt-6">
          <h2 className="text-lg">{section.name}</h2>
          <ul className="mt-2 grid gap-4">
            {section.items.map((item) => (
              <li key={`${section.name}-${item.name}`} data-testid="public-item">
                <p className="text-base">{item.name}</p>
                {item.detail ? <p className="mt-1 text-sm text-muted" data-testid="public-detail">{item.detail}</p> : null}
                <p className="mt-1 text-sm" data-testid="public-price">
                  {item.glass_price_cents ? `Glass ${money(item.glass_price_cents, item.currency)}` : ""}
                  {item.glass_price_cents && item.bottle_price_cents ? " · " : ""}
                  {item.bottle_price_cents ? `Bottle ${money(item.bottle_price_cents, item.currency)}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  );
}
