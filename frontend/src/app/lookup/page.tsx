"use client";

import { FormEvent, useEffect, useState } from "react";
import { FloorLookup } from "@/components/FloorLookup";
import { getLookupPack, lookupFloor, type LookupHit } from "@/lib/api";
import { searchPack } from "@/lib/lookupOffline";

export default function LookupPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<LookupHit[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    void getLookupPack().catch(() => undefined);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const disconnected = typeof navigator !== "undefined" && !navigator.onLine;
    try {
      if (disconnected) {
        setResults(searchPack(await getLookupPack(), query));
        setOffline(true);
        return;
      }
      const body = await lookupFloor(query);
      setOffline(false);
      setResults(body.results);
    } catch (exc) {
      try {
        setResults(searchPack(await getLookupPack(), query));
        setOffline(true);
      } catch {
        setResults(null);
        setOffline(false);
        setError(exc instanceof Error ? exc.message : "Lookup did not load.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="h-page">Floor lookup</h1>
      <form className="space-y-2" onSubmit={onSubmit}>
        <label className="text-sm" htmlFor="lookup-query">
          Dish, bottle, or preference
        </label>
        <div className="flex gap-2">
          <input
            id="lookup-query"
            className="field min-h-11 flex-1"
            data-testid="lookup-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Oaky Chardonnay under $80"
          />
          <button type="submit" className="btn btn-primary" data-testid="lookup-submit" disabled={busy}>
            Search
          </button>
        </div>
      </form>
      {offline ? (
        <p className="text-sm text-[var(--muted)]" data-testid="lookup-offline">
          Showing the list saved on this phone.
        </p>
      ) : null}
      {error ? (
        <p className="text-sm" role="alert">
          {error}
        </p>
      ) : null}
      {results ? <FloorLookup results={results} /> : null}
    </div>
  );
}
