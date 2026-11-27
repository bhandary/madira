"use client";

import { FormEvent, useState } from "react";
import { searchCatalog, type CatalogSearchResult } from "@/lib/api";

export function CatalogSearch() {
  const [query, setQuery] = useState("");
  const [body, setBody] = useState<CatalogSearchResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setBody(await searchCatalog(query));
    } catch (exc) {
      setBody(null);
      setError(exc instanceof Error ? exc.message : "Catalog search failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="mt-4 space-y-2" onSubmit={onSubmit}>
      <label className="text-sm" htmlFor="catalog-search">
        Search the catalog
      </label>
      <div className="flex gap-2">
        <input
          id="catalog-search"
          className="field min-h-11 flex-1"
          data-testid="catalog-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Barolo, kriek, saline"
        />
        <button type="submit" className="btn btn-primary" data-testid="catalog-search-submit" disabled={busy}>
          Search
        </button>
      </div>
      {error ? (
        <p className="text-sm" role="alert">
          {error}
        </p>
      ) : null}
      {body ? (
        <div className="space-y-2" data-testid="catalog-results">
          <p className="text-sm text-muted" data-testid="catalog-search-mode">
            {body.mode === "semantic" ? "Ranked by taste similarity." : "Matched the catalog words."}
          </p>
          {body.results.length === 0 ? <p className="text-sm">No catalog match.</p> : null}
          <ul className="grid gap-2">
            {body.results.map((hit) => (
              <li
                key={hit.sku_id}
                className="panel p-3"
                data-testid="catalog-hit"
                data-name={hit.name}
              >
                <div className="text-sm font-medium">{hit.name}</div>
                <div className="text-xs text-muted">
                  {[hit.producer, hit.region, hit.style, hit.category].filter(Boolean).join(" · ")}
                </div>
                <p className="mt-1 text-sm">{hit.why}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </form>
  );
}
