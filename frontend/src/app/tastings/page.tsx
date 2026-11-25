"use client";

import { useEffect, useState } from "react";
import { SampleCard } from "@/components/SampleCard";
import { TastingInvitePanel } from "@/components/TastingInvite";
import type { SampleCardData, SampleProductOption } from "@/a2ui/sampleCardSchema";
import {
  ApiError,
  addSample,
  createTastingSession,
  draftRepFollowup,
  getProducts,
  getRepFollowup,
  getTastingSession,
  listProcurementSuppliers,
  listTastingSessions,
  type RepFollowup,
  type TastingSessionRow,
} from "@/lib/api";

export default function TastingsPage() {
  const [ready, setReady] = useState(false);
  const [suppliers, setSuppliers] = useState<{ id: string; name: string }[]>([]);
  const [products, setProducts] = useState<SampleProductOption[]>([]);
  const [sessions, setSessions] = useState<TastingSessionRow[]>([]);
  const [selected, setSelected] = useState("");
  const [samples, setSamples] = useState<SampleCardData[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("2026-12-01T15:00");
  const [location, setLocation] = useState("Maison Madira cellar");
  const [followup, setFollowup] = useState<RepFollowup | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([listProcurementSuppliers(), listTastingSessions(), getProducts()])
      .then(([supplierBody, sessionBody, productBody]) => {
        if (cancelled) return;
        setSuppliers(supplierBody.suppliers.map((row) => ({ id: row.id, name: row.name })));
        setSessions(sessionBody.sessions);
        setProducts(productBody.products.map((row) => ({ id: row.id, name: row.name })));
        const kermit = supplierBody.suppliers.find((row) => row.name === "Kermit Lynch Wine Merchant");
        if (kermit) setSupplierId(kermit.id);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "The tasting calendar could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function openSession(sessionId: string) {
    const body = await getTastingSession(sessionId);
    const note = await getRepFollowup(sessionId);
    setSelected(sessionId);
    setSamples(body.samples);
    setFollowup(note.followup);
    setCopied(false);
    setSessions((current) => {
      const next = current.filter((row) => row.id !== body.session.id);
      return [body.session, ...next];
    });
  }

  async function plan() {
    setBusy(true);
    setError("");
    try {
      const body = await createTastingSession({
        supplier_id: supplierId,
        title,
        starts_at: when,
        location,
      });
      await openSession(body.draft.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The tasting could not be planned.");
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await addSample(selected);
      await openSession(selected);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The sample could not be added.");
    } finally {
      setBusy(false);
    }
  }

  const current = sessions.find((row) => row.id === selected);

  return (
    <div className="mx-auto w-full max-w-lg">
      <h1 className="h-page">Tasting sessions</h1>
      <p className="mt-2 text-sm text-muted">
        Plan a cellar tasting and score the samples. The calendar file is a download. Nothing is sent.
      </p>

      <form
        className="panel mt-4 space-y-3 p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void plan();
        }}
      >
        <label className="block text-sm">
          Supplier
          <select
            className="field mt-1 min-h-11 w-full"
            data-testid="tasting-supplier"
            value={supplierId}
            disabled={!ready || busy}
            onChange={(event) => setSupplierId(event.target.value)}
          >
            <option value="">Choose a supplier</option>
            {suppliers.map((supplier) => (
              <option key={supplier.id} value={supplier.id}>
                {supplier.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Title
          <input
            className="field mt-1 min-h-11 w-full"
            data-testid="tasting-title"
            value={title}
            disabled={!ready || busy}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          When
          <input
            className="field mt-1 min-h-11 w-full"
            data-testid="tasting-when"
            type="datetime-local"
            value={when}
            disabled={!ready || busy}
            onChange={(event) => setWhen(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          Location
          <input
            className="field mt-1 min-h-11 w-full"
            data-testid="tasting-location"
            value={location}
            disabled={!ready || busy}
            onChange={(event) => setLocation(event.target.value)}
          />
        </label>
        <button className="btn btn-primary min-h-11 w-full" data-testid="tasting-plan" type="submit" disabled={!ready || busy}>
          Plan tasting
        </button>
      </form>

      {sessions.length ? (
        <ul className="mt-4 space-y-2" data-testid="tasting-sessions">
          {sessions.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                className="btn min-h-11 w-full justify-start text-left"
                data-testid="tasting-session"
                aria-current={row.id === selected ? "true" : undefined}
                onClick={() => {
                  void openSession(row.id).catch((err: unknown) => {
                    setError(err instanceof ApiError ? err.message : "The tasting could not be opened.");
                  });
                }}
              >
                {row.title} · {row.starts_at}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {current ? (
        <section className="mt-4 space-y-3" data-testid="tasting-open">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-medium" data-testid="tasting-session-title">
              {current.title}
            </h2>
            <a
              className="btn btn-primary inline-flex min-h-11 items-center"
              data-testid="tasting-ics"
              href={`/madira-api/tastings/${current.id}.ics`}
              download={`${current.title || "tasting"}.ics`}
            >
              Download .ics
            </a>
          </div>
          <p className="text-sm text-muted">
            {current.supplier} · {current.starts_at} → {current.ends_at} · {current.location}
          </p>
          <button className="btn min-h-11 w-full" data-testid="tasting-add-sample" type="button" disabled={busy} onClick={() => void add()}>
            Add sample
          </button>
          <div className="space-y-3">
            {samples.map((sample) => (
              <SampleCard
                key={`${sample.id}:${sample.score ?? ""}:${sample.product_id ?? ""}:${sample.quoted_price_cents ?? ""}:${sample.decision}:${sample.pass_reason}:${sample.purchase_order_id ?? ""}:${sample.list_version_id ?? ""}:${sample.label_document_id ?? ""}`}
                sample={sample}
                products={products}
                onChange={(next) => {
                  setSamples((currentSamples) => currentSamples.map((row) => (row.id === next.id ? next : row)));
                }}
              />
            ))}
          </div>
          <TastingInvitePanel key={current.id} sessionId={current.id} />
          <section className="panel space-y-3 p-3" data-testid="followup-panel">
            <h3 className="text-base font-medium">Rep follow-up</h3>
            <p className="text-sm text-muted">A draft for the supplier. Madira does not send it.</p>
            <button
              type="button"
              className="btn btn-primary min-h-11 w-full"
              data-testid="tasting-followup"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                setError("");
                void draftRepFollowup(current.id)
                  .then((body) => setFollowup(body.followup))
                  .catch((err: unknown) => {
                    setError(err instanceof ApiError ? err.message : "The follow-up could not be drafted.");
                  })
                  .finally(() => setBusy(false));
              }}
            >
              Draft follow-up
            </button>
            {followup ? (
              <div className="space-y-2">
                <p className="text-sm font-medium" data-testid="followup-subject">
                  {followup.subject}
                </p>
                <pre className="whitespace-pre-wrap text-sm" data-testid="followup-body">
                  {followup.body}
                </pre>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn min-h-11"
                    data-testid="followup-copy"
                    onClick={() => {
                      void navigator.clipboard.writeText(followup.body).then(() => setCopied(true));
                    }}
                  >
                    {copied ? "Copied" : "Copy draft"}
                  </button>
                  {followup.mailto ? (
                    <a className="btn inline-flex min-h-11 items-center" data-testid="followup-mailto" href={followup.mailto}>
                      Open in mail
                    </a>
                  ) : (
                    <p className="text-sm text-muted">No rep email is on file.</p>
                  )}
                </div>
              </div>
            ) : null}
          </section>
        </section>
      ) : null}

      {error ? <p className="mt-3 text-sm text-alert">{error}</p> : null}
    </div>
  );
}
