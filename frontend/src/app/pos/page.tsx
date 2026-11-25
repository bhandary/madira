"use client";

import { useEffect, useState } from "react";
import { posStatus, unmappedPosItem } from "@/a2ui/posSchema";
import { PosStatusView, UnmappedPosView } from "@/components/PosViews";
import {
  ApiError,
  choosePosLocation,
  connectDemoPos,
  connectSquarePos,
  getInventory,
  getPosCatalog,
  getPosGaps,
  getPosMappings,
  getPosRuns,
  getPosStatus,
  savePosMapping,
  syncPos,
  type PosCatalogItem,
  type PosMapping,
  type PosRun,
  type PosStatus,
} from "@/lib/api";

type SkuOption = { sku: string; name: string };

function message(err: unknown) {
  return err instanceof ApiError ? err.message : "The register could not be updated.";
}

export default function PosPage() {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<PosStatus | null>(null);
  const [items, setItems] = useState<PosCatalogItem[]>([]);
  const [mappings, setMappings] = useState<PosMapping[]>([]);
  const [runs, setRuns] = useState<PosRun[]>([]);
  const [gaps, setGaps] = useState<{ variation_id: string; item_id: string; name: string; quantity: string }[]>([]);
  const [skus, setSkus] = useState<SkuOption[]>([]);
  const [token, setToken] = useState("");
  const [locationId, setLocationId] = useState("");
  const [choices, setChoices] = useState<{ location_id: string; name: string }[]>([]);

  function applyStatus(next: PosStatus) {
    const parsed = posStatus.safeParse(next);
    setStatus(parsed.success ? parsed.data : next);
    if (next.locations?.length) setChoices(next.locations);
  }

  async function loadDesk(current: PosStatus) {
    const stock = await getInventory();
    const options = Array.isArray(stock?.items)
      ? stock.items.map((item: { sku?: string; name?: string }) => ({ sku: item.sku || "", name: item.name || "" }))
      : [];
    setSkus(options.filter((item: SkuOption) => item.sku));
    if (!current.connected && current.status !== "pending") {
      setItems([]);
      setMappings([]);
      setRuns([]);
      setGaps([]);
      return;
    }
    const [catalog, mapped, history, open] = await Promise.all([
      current.status === "active" || current.connected ? getPosCatalog() : Promise.resolve({ items: [] }),
      getPosMappings(),
      getPosRuns(),
      getPosGaps(),
    ]);
    setItems(catalog.items);
    setMappings(mapped.mappings);
    setRuns(history.runs);
    setGaps(open.items.filter((item) => unmappedPosItem.safeParse(item).success));
  }

  useEffect(() => {
    let cancelled = false;
    getPosStatus()
      .then((next) => {
        if (cancelled) return;
        applyStatus(next);
        return loadDesk(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err));
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function refresh(next: PosStatus) {
    applyStatus(next);
    await loadDesk(next);
  }

  async function onConnectDemo() {
    setBusy(true);
    setError("");
    try {
      await refresh(await connectDemoPos());
    } catch (err: unknown) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function onConnectSquare() {
    setBusy(true);
    setError("");
    try {
      const next = await connectSquarePos(token, locationId);
      setToken("");
      await refresh(next);
    } catch (err: unknown) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function onLocation() {
    setBusy(true);
    setError("");
    try {
      await refresh(await choosePosLocation(locationId));
    } catch (err: unknown) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function onMap(item: PosCatalogItem, form: FormData) {
    setBusy(true);
    setError("");
    try {
      const pour = String(form.get("pour_ml") || "").trim();
      await savePosMapping({
        variation_id: item.variation_id,
        item_id: item.item_id,
        sku: String(form.get("sku") || ""),
        pour_ml: pour ? Number(pour) : null,
        units_per_sale: String(form.get("units_per_sale") || "1"),
      });
      if (status) await refresh(status);
    } catch (err: unknown) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSync() {
    setBusy(true);
    setError("");
    try {
      await syncPos();
      const next = await getPosStatus();
      await refresh(next);
    } catch (err: unknown) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  const parsed = status ? posStatus.safeParse(status) : null;
  const card = parsed?.success ? parsed.data : null;
  const active = status?.connected === true;

  return (
    <div className="mx-auto w-full min-w-0 max-w-lg space-y-4">
      <header>
        <h1 className="h-page">POS</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Square sales post to the cellar. The token stays on the server.</p>
      </header>
      {error ? (
        <p className="banner-error" role="alert" data-testid="pos-error">
          {error}
        </p>
      ) : null}
      {card ? <PosStatusView status={card} /> : null}
      {status?.connected ? (
        <p className="text-sm" data-testid="pos-connected">
          Connected to {status.location_name || status.provider}
          {status.masked ? ` · ${status.masked}` : ""}
        </p>
      ) : null}

      {status && !status.connected && status.demo_mode ? (
        <button
          type="button"
          className="btn btn-primary min-h-11 w-full"
          data-testid="pos-connect"
          disabled={!ready || busy}
          onClick={() => void onConnectDemo()}
        >
          Connect the demo register
        </button>
      ) : null}

      {status && !status.connected && !status.demo_mode ? (
        <form
          className="panel min-w-0 space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void onConnectSquare();
          }}
        >
          <label className="lbl" htmlFor="square-token">
            Square access token
            <input
              id="square-token"
              className="field w-full min-w-0 max-w-full"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(event) => setToken(event.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary min-h-11 w-full" disabled={!ready || busy || !token}>
            Connect Square
          </button>
        </form>
      ) : null}

      {status?.status === "pending" && choices.length ? (
        <form
          className="panel min-w-0 space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void onLocation();
          }}
        >
          <label className="lbl" htmlFor="pos-location">
            Square location
            <select
              id="pos-location"
              className="field w-full min-w-0 max-w-full"
              value={locationId}
              onChange={(event) => setLocationId(event.target.value)}
            >
              <option value="">Choose a location</option>
              {choices.map((place) => (
                <option key={place.location_id} value={place.location_id}>
                  {place.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="btn btn-primary min-h-11 w-full" disabled={!ready || busy || !locationId}>
            Use this location
          </button>
        </form>
      ) : null}

      {active ? (
        <button
          type="button"
          className="btn btn-primary min-h-11 w-full"
          data-testid="pos-sync"
          disabled={!ready || busy}
          onClick={() => void onSync()}
        >
          Sync sales
        </button>
      ) : null}

      {active ? (
        <section className="space-y-3" aria-labelledby="pos-map-heading">
          <h2 id="pos-map-heading" className="text-base font-semibold">
            Map items
          </h2>
          {items.map((item) => {
            const mapping = mappings.find((row) => row.variation_id === item.variation_id);
            return (
              <form
                key={item.variation_id}
                className="panel min-w-0 max-w-full space-y-2 overflow-hidden"
                data-testid="pos-item"
                data-variation={item.variation_id}
                onSubmit={(event) => {
                  event.preventDefault();
                  void onMap(item, new FormData(event.currentTarget));
                }}
              >
                <p className="break-words text-sm font-medium">
                  {item.name}
                  {item.variation_name ? ` · ${item.variation_name}` : ""}
                </p>
                <label className="lbl" htmlFor={`sku-${item.variation_id}`}>
                  SKU
                  <select
                    id={`sku-${item.variation_id}`}
                    name="sku"
                    className="field w-full min-w-0 max-w-full"
                    defaultValue={mapping?.sku || item.sku_hint || ""}
                  >
                    <option value="">Choose a SKU</option>
                    {skus.map((sku) => (
                      <option key={sku.sku} value={sku.sku}>
                        {sku.sku} {sku.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid min-w-0 grid-cols-2 gap-2">
                  <label className="lbl min-w-0" htmlFor={`pour-${item.variation_id}`}>
                    Pour ml
                    <input
                      id={`pour-${item.variation_id}`}
                      name="pour_ml"
                      className="field w-full min-w-0 max-w-full"
                      inputMode="numeric"
                      defaultValue={mapping?.pour_ml ?? ""}
                    />
                  </label>
                  <label className="lbl min-w-0" htmlFor={`units-${item.variation_id}`}>
                    Units per sale
                    <input
                      id={`units-${item.variation_id}`}
                      name="units_per_sale"
                      className="field w-full min-w-0 max-w-full"
                      inputMode="decimal"
                      defaultValue={mapping?.units_per_sale ?? 1}
                    />
                  </label>
                </div>
                <button type="submit" className="btn btn-secondary min-h-11 w-full whitespace-normal" disabled={!ready || busy}>
                  Save mapping
                </button>
              </form>
            );
          })}
        </section>
      ) : null}

      <UnmappedPosView items={gaps} />

      <section className="panel min-w-0" data-testid="pos-history">
        <h2 className="text-base font-semibold">Sync history</h2>
        {runs.length ? (
          <ul className="mt-2 space-y-2 text-sm">
            {runs.map((run) => (
              <li key={run.id} className="break-words" data-testid="pos-run">
                {run.status} · posted {run.posted} · skipped {run.skipped} · unmapped {run.unmapped_count}
                {run.error ? ` · ${run.error}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--muted)]">No syncs yet.</p>
        )}
      </section>
    </div>
  );
}
