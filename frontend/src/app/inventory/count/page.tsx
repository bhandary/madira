"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CountSheet, formatCount } from "@/components/CountSheet";
import { VarianceReport, type VarianceReportData } from "@/components/VarianceReport";
import {
  ApiError,
  acceptParProposal,
  approveCountSession,
  generateParProposals,
  getCellar,
  getCountSession,
  listCountSessions,
  listLocations,
  listParProposals,
  rejectParProposal,
  resolveCountConflict,
  startCountSession,
  submitCountSession,
  syncCountLines,
  type CellarLocation,
  type CountReport,
  type CountSessionRecord,
  type ParProposalRecord,
  type StockItem,
} from "@/lib/api";
import { clearOpenSheet, clearQueue, deviceId, mutationId, readOpenSheet, readQueue, writeOpenSheet, writeQueue, type QueuedCount } from "@/lib/countQueue";

function reportView(report: CountReport): VarianceReportData {
  return {
    session: report.session,
    lines: report.variance_lines,
    conflicts: report.conflicts,
  };
}

export default function CountPage() {
  const [locations, setLocations] = useState<CellarLocation[]>([]);
  const [items, setItems] = useState<StockItem[]>([]);
  const [openSessions, setOpenSessions] = useState<CountSessionRecord[]>([]);
  const [locationId, setLocationId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [sessionName, setSessionName] = useState("");
  const [sessionStatus, setSessionStatus] = useState("");
  const [lines, setLines] = useState<CountReport["lines"]>([]);
  const [report, setReport] = useState<CountReport | null>(null);
  const [search, setSearch] = useState("");
  const [sku, setSku] = useState("");
  const [binQr, setBinQr] = useState("");
  const [quantity, setQuantity] = useState("0");
  const [queued, setQueued] = useState<QueuedCount[]>([]);
  const [proposals, setProposals] = useState<ParProposalRecord[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const proposalLoad = useRef(0);

  const refreshProposals = useCallback(async () => {
    const token = ++proposalLoad.current;
    const body = await listParProposals("pending");
    if (token === proposalLoad.current) setProposals(body.proposals || []);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = ++proposalLoad.current;
    Promise.all([listLocations(), getCellar(), listCountSessions(), listParProposals("pending")])
      .then(([places, cellar, sessions, pars]) => {
        if (cancelled) return;
        setLocations(places.locations || []);
        setItems(cellar.items || []);
        const cellarPlace = (places.locations || []).find((place) => place.name === "Main Cellar");
        setLocationId((current) => current || cellarPlace?.id || places.locations?.[0]?.id || "");
        if (token === proposalLoad.current) setProposals(pars.proposals || []);
        setOpenSessions((sessions.sessions || []).filter((row) => row.status === "in_progress"));
        setLoaded(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const saved = typeof navigator !== "undefined" && !navigator.onLine ? readOpenSheet() : null;
        if (saved) {
          setLocations(saved.locations);
          setItems(saved.items.map((item) => ({ ...item, on_hand: 0, par: 0, low: false, unit: "btl", depletion_30d: 0, valuation_cents: 0, currency: "USD", locations: [] })));
          setLocationId(saved.locationId);
          setSessionId(saved.sessionId);
          setSessionName(saved.locationName);
          setSessionStatus(saved.status);
          setLines(saved.lines);
          setQueued(readQueue(saved.sessionId));
          setLoaded(true);
          return;
        }
        setLoaded(true);
        setError(err instanceof Error ? err.message : "The count could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionId || sessionStatus !== "in_progress") return;
    writeOpenSheet({
      sessionId,
      locationId,
      locationName: sessionName,
      status: sessionStatus,
      items: items.map((item) => ({ sku: item.sku, name: item.name })),
      locations: locations.map((place) => ({ id: place.id, name: place.name, kind: place.kind, notes: place.notes })),
      lines: lines.map((line) => ({
        id: line.id,
        sku: line.sku,
        name: line.name,
        counted_quantity: line.counted_quantity,
        expected_quantity: line.expected_quantity ?? null,
        device_id: line.device_id,
        bin_code: line.bin_code || "",
        counted_at: line.counted_at ?? null,
      })),
    });
  }, [items, lines, locationId, locations, sessionId, sessionName, sessionStatus]);

  const loadSession = useCallback(async (id: string) => {
    const body = await getCountSession(id);
    setLines(body.lines || []);
    setSessionStatus(body.session.status);
    setSessionName(body.session.location_name);
    if (body.session.status !== "in_progress") setReport(body);
    return body;
  }, []);

  useEffect(() => {
    if (!sessionId || sessionStatus !== "in_progress") return;
    let cancelled = false;
    getCountSession(sessionId)
      .then((body) => {
        if (!cancelled) setLines(body.lines || []);
      })
      .catch(() => {
        // The sheet can stay empty until the next sync.
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, sessionStatus]);

  const flush = useCallback(
    async (id: string) => {
      const pending = readQueue(id);
      if (!pending.length) {
        setQueued([]);
        return;
      }
      if (typeof navigator !== "undefined" && !navigator.onLine) return;
      await syncCountLines(id, pending);
      clearQueue(id);
      setQueued([]);
      await loadSession(id);
    },
    [loadSession],
  );

  useEffect(() => {
    if (!sessionId) return;
    const onOnline = () => {
      void flush(sessionId).catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Sync failed.");
      });
    };
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [flush, sessionId]);

  const choices = useMemo(() => {
    const query = search.trim().toLowerCase();
    return items.filter((item) => {
      if (!query) return true;
      return item.sku.toLowerCase().includes(query) || item.name.toLowerCase().includes(query);
    });
  }, [items, search]);

  const selectedSku = useMemo(() => {
    if (sku && choices.some((item) => item.sku === sku)) return sku;
    return choices[0]?.sku || "";
  }, [choices, sku]);

  async function start() {
    setBusy(true);
    setError("");
    try {
      const created = await startCountSession(locationId);
      setSessionId(created.id);
      setSessionName(created.location_name);
      setSessionStatus(created.status);
      setLines([]);
      setReport(null);
      setQueued(readQueue(created.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The count could not be started.");
    } finally {
      setBusy(false);
    }
  }

  function buildEntry(): QueuedCount {
    const countedAt = new Date().toISOString();
    const parsed = Number(quantity);
    const counted = Number.isFinite(parsed) ? Math.round(parsed * 100) / 100 : 0;
    const draft = {
      device_id: deviceId(),
      sku: selectedSku,
      counted_quantity: counted < 0 ? 0 : counted,
      counted_at: countedAt,
      bin_qr: binQr.trim() || undefined,
    };
    return { ...draft, client_mutation_id: mutationId(draft) };
  }

  async function saveCount() {
    if (!sessionId || !selectedSku) return;
    setBusy(true);
    setError("");
    const entry = buildEntry();
    const pending = writeQueue(sessionId, [...readQueue(sessionId), entry]);
    setQueued(pending);
    const offline = typeof navigator !== "undefined" && !navigator.onLine;
    if (offline) {
      setBusy(false);
      return;
    }
    try {
      await syncCountLines(sessionId, pending);
      clearQueue(sessionId);
      setQueued([]);
      await loadSession(sessionId);
    } catch (err) {
      if (err instanceof ApiError && err.status < 500) {
        const kept = readQueue(sessionId).filter((row) => row.client_mutation_id !== entry.client_mutation_id);
        writeQueue(sessionId, kept);
        setQueued(kept);
        setError(err.message);
      } else {
        setError("");
      }
    } finally {
      setBusy(false);
    }
  }

  async function syncNow() {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      await flush(sessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed.");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      if (readQueue(sessionId).length) {
        if (typeof navigator !== "undefined" && !navigator.onLine) {
          setError("Sync the offline queue before submitting.");
          return;
        }
        await flush(sessionId);
      }
      const body = await submitCountSession(sessionId);
      setReport(body);
      setLines(body.lines || []);
      setSessionStatus(body.session.status);
      clearOpenSheet();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The count could not be submitted.");
    } finally {
      setBusy(false);
    }
  }

  async function resolve(skuCode: string, next: number) {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const body = await resolveCountConflict(sessionId, skuCode, next);
      setReport(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The conflict could not be resolved.");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const body = await approveCountSession(sessionId);
      setReport(body);
      setSessionStatus(body.session.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The variance could not be approved.");
    } finally {
      setBusy(false);
    }
  }

  function step(delta: number) {
    setQuantity((current) => {
      const base = Number(current);
      const start = Number.isFinite(base) ? base : 0;
      const next = Math.round((start + delta) * 10) / 10;
      return formatCount(next < 0 ? 0 : next);
    });
  }

  const counting = sessionId && sessionStatus === "in_progress" && !report;
  const reviewing = report != null;

  return (
    <div className="mx-auto w-full max-w-lg" data-testid="count-page">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-2xl font-medium">Count</h1>
        <Link href="/inventory" className="text-sm">
          Cellar
        </Link>
      </div>
      <p className="mt-1 text-sm text-muted">Count a location on the phone. Tenths are for open spirits.</p>

      {error ? (
        <p className="banner-error mt-3" role="alert" data-testid="count-error">
          {error}
        </p>
      ) : null}

      {!loaded ? <p className="mt-4 text-sm text-muted">Loading locations…</p> : null}

      {loaded && !sessionId ? (
        <form
          className="mt-4 space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void start();
          }}
        >
          <label className="lbl" htmlFor="count-location">
            Location
            <select
              id="count-location"
              data-testid="count-location"
              className="field"
              value={locationId}
              onChange={(event) => setLocationId(event.target.value)}
            >
              {locations.map((place) => (
                <option key={place.id} value={place.id}>
                  {place.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="btn btn-primary w-full" data-testid="count-start" disabled={busy || !locationId}>
            Start count
          </button>
          {openSessions.length > 0 ? (
            <div className="space-y-2">
              {openSessions.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className="btn btn-secondary w-full"
                  data-testid="count-resume"
                  disabled={busy}
                  onClick={() => {
                    setSessionId(row.id);
                    setSessionName(row.location_name);
                    setSessionStatus(row.status);
                    setLocationId(row.location_id);
                    setQueued(readQueue(row.id));
                    setReport(null);
                  }}
                >
                  Resume {row.location_name}
                </button>
              ))}
            </div>
          ) : null}
        </form>
      ) : null}

      {sessionId && counting ? (
        <div className="mt-4 space-y-4">
          <p className="text-sm text-muted">{sessionName}</p>
          {queued.length > 0 ? (
            <p className="panel p-3 text-sm" role="status" data-testid="queued-offline">
              Queued offline ({queued.length})
            </p>
          ) : null}
          <div className="space-y-3">
            <label className="lbl" htmlFor="count-search">
              Search SKU
              <input
                id="count-search"
                data-testid="count-search"
                className="field"
                value={search}
                placeholder="Name or SKU"
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <label className="lbl" htmlFor="count-sku">
              SKU
              <select
                id="count-sku"
                data-testid="count-sku"
                className="field"
                value={selectedSku}
                onChange={(event) => {
                  setSku(event.target.value);
                  setQuantity("0");
                }}
              >
                {choices.map((item) => (
                  <option key={item.sku} value={item.sku}>
                    {item.sku} {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl" htmlFor="count-bin">
              Bin QR
              <input
                id="count-bin"
                data-testid="count-bin"
                className="field font-mono"
                value={binQr}
                placeholder="madira:bin:…"
                onChange={(event) => setBinQr(event.target.value)}
              />
            </label>
            <div className="grid grid-cols-5 gap-2">
              <button type="button" className="btn btn-secondary px-0" data-testid="count-minus-one" onClick={() => step(-1)}>
                -1
              </button>
              <button type="button" className="btn btn-secondary px-0" data-testid="count-minus-tenth" onClick={() => step(-0.1)}>
                -0.1
              </button>
              <input
                id="count-qty"
                data-testid="count-qty"
                aria-label="Quantity"
                className="field px-1 text-center tabular-nums"
                inputMode="decimal"
                value={quantity}
                onChange={(event) => {
                  const next = event.target.value;
                  if (next === "" || /^\d*\.?\d{0,2}$/.test(next)) setQuantity(next);
                }}
              />
              <button type="button" className="btn btn-secondary px-0" data-testid="count-plus-tenth" onClick={() => step(0.1)}>
                +0.1
              </button>
              <button type="button" className="btn btn-secondary px-0" data-testid="count-plus-one" onClick={() => step(1)}>
                +1
              </button>
            </div>
            <button type="button" className="btn btn-primary w-full" data-testid="count-save" disabled={busy || !selectedSku} onClick={() => void saveCount()}>
              Save count
            </button>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" className="btn btn-secondary" data-testid="count-sync" disabled={busy} onClick={() => void syncNow()}>
                Sync now
              </button>
              <button type="button" className="btn btn-secondary" data-testid="count-submit" disabled={busy} onClick={() => void submit()}>
                Submit
              </button>
            </div>
          </div>
          <CountSheet session={{ id: sessionId, status: sessionStatus, location_name: sessionName }} lines={lines} />
        </div>
      ) : null}

      {reviewing && report ? (
        <div className="mt-4">
          <VarianceReport
            report={reportView(report)}
            busy={busy}
            onResolve={(skuCode, next) => void resolve(skuCode, next)}
            onApprove={() => void approve()}
          />
        </div>
      ) : null}

      <section className="mt-8" aria-labelledby="par-heading" data-testid="par-proposals">
        <h2 id="par-heading" className="text-lg font-medium">
          Par proposals
        </h2>
        <p className="mt-1 text-sm text-muted">Suggested par covers lead time plus safety stock from the last 30 days of depletion.</p>
        <button
          type="button"
          className="btn btn-secondary mt-3 w-full"
          data-testid="par-generate"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError("");
            const token = ++proposalLoad.current;
            generateParProposals()
              .then((body) => {
                if (token === proposalLoad.current) setProposals(body.proposals || []);
              })
              .catch((err: unknown) => setError(err instanceof Error ? err.message : "Par proposals could not be generated."))
              .finally(() => setBusy(false));
          }}
        >
          Propose par updates
        </button>
        <ul className="mt-3 space-y-2">
          {proposals.map((proposal) => (
            <li
              key={proposal.id}
              className="panel p-3"
              data-testid="par-proposal"
              data-sku={proposal.sku}
              data-current={proposal.current_par}
              data-proposed={proposal.proposed_par}
            >
              <div className="font-mono text-xs">{proposal.sku}</div>
              <div className="text-sm">{proposal.name}</div>
              <p className="mt-2 text-sm">
                Par {proposal.current_par} → {proposal.proposed_par}
              </p>
              <p className="text-sm text-muted">30-day depletion {proposal.depletion_30d}</p>
              <p className="mt-1 text-sm">{proposal.rationale}</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  className="btn btn-primary"
                  data-testid="par-accept"
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    setError("");
                    acceptParProposal(proposal.id)
                      .then(() => refreshProposals())
                      .catch((err: unknown) => setError(err instanceof Error ? err.message : "The proposal could not be accepted."))
                      .finally(() => setBusy(false));
                  }}
                >
                  Accept
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  data-testid="par-reject"
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    setError("");
                    rejectParProposal(proposal.id)
                      .then(() => refreshProposals())
                      .catch((err: unknown) => setError(err instanceof Error ? err.message : "The proposal could not be rejected."))
                      .finally(() => setBusy(false));
                  }}
                >
                  Reject
                </button>
              </div>
            </li>
          ))}
        </ul>
        {loaded && proposals.length === 0 ? <p className="mt-2 text-sm text-muted">No pending proposals.</p> : null}
      </section>
    </div>
  );
}
