"use client";

import { useEffect, useState } from "react";
import type { SourcingBriefData, TastingHistoryData } from "@/a2ui/sourcingSchema";
import { SourcingBriefView, TastingHistoryView } from "@/components/SourcingViews";
import { ApiError, buildSourcingBrief, getTastingHistory, listSourcingBriefs } from "@/lib/api";

export default function SourcingPage() {
  const [ready, setReady] = useState(false);
  const [brief, setBrief] = useState<SourcingBriefData | null>(null);
  const [history, setHistory] = useState<TastingHistoryData>({ rows: [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([listSourcingBriefs(), getTastingHistory()])
      .then(([briefs, tasted]) => {
        if (cancelled) return;
        setBrief(briefs.briefs[0] ?? null);
        setHistory({ rows: tasted.rows });
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "The sourcing brief could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto w-full max-w-lg">
      <h1 className="h-page">Sourcing</h1>
      <p className="mt-2 text-sm text-muted">
        Gaps from the list become a want list. Quantities come from the cellar, and the note is only a rationale.
      </p>
      <button
        type="button"
        className="btn btn-primary mt-4 min-h-11 w-full"
        data-testid="sourcing-build"
        disabled={!ready || busy}
        onClick={() => {
          setBusy(true);
          setError("");
          void buildSourcingBrief()
            .then(async (body) => {
              setBrief(body.brief);
              const tasted = await getTastingHistory();
              setHistory({ rows: tasted.rows });
            })
            .catch((err: unknown) => {
              setError(err instanceof ApiError ? err.message : "The sourcing brief could not be built.");
            })
            .finally(() => setBusy(false));
        }}
      >
        Build sourcing brief
      </button>
      <div className="mt-4 space-y-6">
        {brief ? <SourcingBriefView brief={brief} /> : <p className="text-sm text-muted">No sourcing brief yet.</p>}
        <TastingHistoryView history={history} />
      </div>
      {error ? <p className="mt-3 text-sm text-alert">{error}</p> : null}
    </div>
  );
}
