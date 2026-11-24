"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  createBin,
  createLocation,
  getBinLabel,
  getCellar,
  listBins,
  listMovements,
  postMovement,
  postTransfer,
  type CellarBin,
  type CellarLocation,
  type StockItem,
  type StockMovementRow,
} from "@/lib/api";

const KINDS = [
  ["cellar", "Cellar"],
  ["bar", "Bar"],
  ["walk_in", "Walk-in"],
  ["storage", "Storage"],
  ["other", "Other"],
] as const;

const MOVEMENTS = [
  ["receive", "Receive"],
  ["sale", "Sale"],
  ["breakage", "Breakage"],
  ["comp", "Comp"],
  ["faulty_bottle", "Faulty bottle"],
  ["return", "Return"],
  ["count_adjustment", "Count adjustment"],
] as const;

const NEGATIVE = new Set(["sale", "breakage", "comp", "faulty_bottle"]);

function formatQty(value: number) {
  if (!Number.isFinite(value)) return "0";
  const rounded = Math.round(value * 100) / 100;
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toFixed(2).replace(/0$/, "");
}

function money(cents: number, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format((cents || 0) / 100);
}

function signedQuantity(movementType: string, raw: number) {
  const qty = Math.round(raw * 100) / 100;
  if (!Number.isFinite(qty) || qty === 0) return qty;
  if (NEGATIVE.has(movementType)) return -Math.abs(qty);
  if (movementType === "receive") return Math.abs(qty);
  return qty;
}

function when(value: string) {
  return value ? value.replace("T", " ").replace(/\.\d+/, "").replace("Z", " UTC") : "";
}

export function CellarBoard({
  revision,
  onStockChanged,
}: {
  revision: number;
  onStockChanged: () => void;
}) {
  const [items, setItems] = useState<StockItem[]>([]);
  const [locations, setLocations] = useState<CellarLocation[]>([]);
  const [bins, setBins] = useState<CellarBin[]>([]);
  const [movements, setMovements] = useState<StockMovementRow[]>([]);
  const [filter, setFilter] = useState("all");
  const [panel, setPanel] = useState<"stock" | "ledger" | "places">("stock");
  const [sku, setSku] = useState("W-MUS-01");
  const [movementType, setMovementType] = useState("receive");
  const [movementQty, setMovementQty] = useState("1");
  const [movementLocation, setMovementLocation] = useState("");
  const [reason, setReason] = useState("");
  const [transferSku, setTransferSku] = useState("W-MUS-01");
  const [transferFrom, setTransferFrom] = useState("");
  const [transferTo, setTransferTo] = useState("");
  const [transferQty, setTransferQty] = useState("1");
  const [locationName, setLocationName] = useState("");
  const [locationKind, setLocationKind] = useState("storage");
  const [binLocation, setBinLocation] = useState("");
  const [binCode, setBinCode] = useState("");
  const [binLabel, setBinLabel] = useState("");
  const [labelSvg, setLabelSvg] = useState("");
  const [labelPayload, setLabelPayload] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getCellar(), listBins(), listMovements()])
      .then(([cellar, binBody, ledger]) => {
        if (cancelled) return;
        const places = cellar.locations || [];
        setItems(cellar.items || []);
        setLocations(places);
        setBins(binBody.bins || []);
        setMovements(ledger.movements || []);
        setMovementLocation((current) => current || places[0]?.id || "");
        setTransferFrom((current) => current || places.find((place) => place.name === "Main Cellar")?.id || places[0]?.id || "");
        setTransferTo((current) => current || places.find((place) => place.name === "Main Bar")?.id || places[1]?.id || "");
        setBinLocation((current) => current || places[0]?.id || "");
        setLoaded(true);
        setError("");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoaded(true);
        setError(err instanceof Error ? err.message : "The cellar could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [revision]);

  const visible = items.filter((item) => {
    if (filter === "all") return true;
    const place = item.locations?.find((row) => row.location_id === filter);
    return !!place && place.quantity !== 0;
  });

  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await task();
      onStockChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  function recordMovement(event: FormEvent) {
    event.preventDefault();
    const quantity = signedQuantity(movementType, Number(movementQty));
    if (!sku || !movementLocation || !quantity) {
      setError("Choose a SKU, a location, and a non-zero quantity.");
      return;
    }
    void run(() =>
      postMovement({
        sku,
        location_id: movementLocation,
        movement_type: movementType,
        quantity,
        reason,
      }).then(() => undefined),
    );
  }

  function transfer(event: FormEvent) {
    event.preventDefault();
    const quantity = Math.abs(Math.round(Number(transferQty) * 100) / 100);
    if (!transferSku || !transferFrom || !transferTo || !quantity) {
      setError("Choose two locations and a quantity to transfer.");
      return;
    }
    void run(() =>
      postTransfer({
        sku: transferSku,
        from_location_id: transferFrom,
        to_location_id: transferTo,
        quantity,
        reason: "Transfer",
      }).then(() => undefined),
    );
  }

  function addLocation(event: FormEvent) {
    event.preventDefault();
    if (!locationName.trim()) {
      setError("Name the location.");
      return;
    }
    void run(async () => {
      await createLocation({ name: locationName.trim(), kind: locationKind });
      setLocationName("");
    });
  }

  function addBin(event: FormEvent) {
    event.preventDefault();
    if (!binLocation || !binCode.trim()) {
      setError("Choose a location and a bin code.");
      return;
    }
    void run(async () => {
      await createBin({ location_id: binLocation, code: binCode.trim(), label: binLabel.trim() });
      setBinCode("");
      setBinLabel("");
    });
  }

  async function showLabel(binId: string) {
    setBusy(true);
    setError("");
    try {
      const label = await getBinLabel(binId);
      setLabelSvg(label.svg);
      setLabelPayload(label.qr_payload);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "The label could not be loaded.");
    } finally {
      setBusy(false);
    }
  }

  function printLabel() {
    if (!labelSvg) return;
    const popup = window.open("", "_blank", "noopener,noreferrer");
    if (!popup) return;
    popup.document.write(`<!doctype html><title>Bin label</title><body style="margin:24px">${labelSvg}<p>${labelPayload}</p></body>`);
    popup.document.close();
    popup.focus();
    popup.print();
  }

  return (
    <section className="mt-6" aria-labelledby="cellar-board-heading" data-testid="cellar-board">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="cellar-board-heading" className="text-lg font-medium">
          Cellar ledger
        </h2>
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Cellar sections">
          {(
            [
              ["stock", "Stock"],
              ["ledger", "Movements"],
              ["places", "Locations & bins"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className="btn btn-segment"
              data-testid={`cellar-tab-${id}`}
              aria-pressed={panel === id}
              onClick={() => setPanel(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <p className="banner-error mt-3" role="alert" data-testid="cellar-error">
          {error}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2" role="tablist" aria-label="Locations">
        <button
          type="button"
          className="btn btn-segment"
          data-testid="location-pill"
          data-location="all"
          aria-pressed={filter === "all"}
          onClick={() => setFilter("all")}
        >
          All locations
        </button>
        {locations.map((place) => (
          <button
            key={place.id}
            type="button"
            className="btn btn-segment"
            data-testid="location-pill"
            data-location={place.name}
            aria-pressed={filter === place.id}
            onClick={() => setFilter(place.id)}
          >
            {place.name}
          </button>
        ))}
      </div>

      {panel === "stock" ? (
        <div className="mt-4 space-y-4">
          <form className="flex flex-wrap items-end gap-3" onSubmit={recordMovement}>
            <label className="lbl" htmlFor="movement-sku">
              SKU
              <select
                id="movement-sku"
                data-testid="movement-sku"
                className="field w-40"
                value={sku}
                onChange={(event) => setSku(event.target.value)}
              >
                {items.map((item) => (
                  <option key={item.sku} value={item.sku}>
                    {item.sku}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl" htmlFor="movement-type">
              Movement
              <select
                id="movement-type"
                data-testid="movement-type"
                className="field w-44"
                value={movementType}
                onChange={(event) => setMovementType(event.target.value)}
              >
                {MOVEMENTS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl" htmlFor="movement-qty">
              Quantity
              <input
                id="movement-qty"
                data-testid="movement-qty"
                className="field w-28"
                type="number"
                step="0.1"
                value={movementQty}
                onChange={(event) => setMovementQty(event.target.value)}
              />
            </label>
            <label className="lbl" htmlFor="movement-location">
              Location
              <select
                id="movement-location"
                data-testid="movement-location"
                className="field w-44"
                value={movementLocation}
                onChange={(event) => setMovementLocation(event.target.value)}
              >
                {locations.map((place) => (
                  <option key={place.id} value={place.id}>
                    {place.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl min-w-40 flex-1" htmlFor="movement-reason">
              Reason
              <input
                id="movement-reason"
                data-testid="movement-reason"
                className="field"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <button type="submit" className="btn btn-secondary" data-testid="movement-submit" disabled={busy}>
              Record movement
            </button>
          </form>

          <form className="flex flex-wrap items-end gap-3" onSubmit={transfer}>
            <label className="lbl" htmlFor="transfer-sku">
              Transfer SKU
              <select
                id="transfer-sku"
                data-testid="transfer-sku"
                className="field w-40"
                value={transferSku}
                onChange={(event) => setTransferSku(event.target.value)}
              >
                {items.map((item) => (
                  <option key={item.sku} value={item.sku}>
                    {item.sku}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl" htmlFor="transfer-from">
              From
              <select
                id="transfer-from"
                data-testid="transfer-from"
                className="field w-44"
                value={transferFrom}
                onChange={(event) => setTransferFrom(event.target.value)}
              >
                {locations.map((place) => (
                  <option key={place.id} value={place.id}>
                    {place.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl" htmlFor="transfer-to">
              To
              <select
                id="transfer-to"
                data-testid="transfer-to"
                className="field w-44"
                value={transferTo}
                onChange={(event) => setTransferTo(event.target.value)}
              >
                {locations.map((place) => (
                  <option key={place.id} value={place.id}>
                    {place.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl" htmlFor="transfer-qty">
              Quantity
              <input
                id="transfer-qty"
                data-testid="transfer-qty"
                className="field w-28"
                type="number"
                min="0.1"
                step="0.1"
                value={transferQty}
                onChange={(event) => setTransferQty(event.target.value)}
              />
            </label>
            <button type="submit" className="btn btn-secondary" data-testid="transfer-submit" disabled={busy}>
              Transfer
            </button>
          </form>

          <div className="space-y-2" data-testid="cellar-stock">
            {visible.map((item) => (
              <article key={item.sku} className="panel p-3" data-testid="sku-row" data-sku={item.sku}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="min-w-0">
                    <span className="font-mono text-xs">{item.sku}</span>
                    <span className="ml-2 text-sm">{item.name}</span>
                  </div>
                  <div className="text-sm">
                    On hand <span data-testid="sku-on-hand">{formatQty(item.on_hand)}</span>
                    {item.low ? " · low" : ""}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                  {(item.locations || []).map((place) => (
                    <span
                      key={place.location_id}
                      data-testid="location-qty"
                      data-location={place.location_name}
                      data-qty={String(place.quantity)}
                    >
                      {place.location_name} {formatQty(place.quantity)}
                    </span>
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted">
                  Par <span data-testid="sku-par">{item.par}</span> · 30-day depletion {formatQty(item.depletion_30d)} ·{" "}
                  {money(item.valuation_cents, item.currency)}
                </p>
              </article>
            ))}
            {loaded && visible.length === 0 ? <p className="text-sm text-muted">No stock in this location.</p> : null}
            {!loaded ? <p className="text-sm text-muted">Loading locations…</p> : null}
          </div>
        </div>
      ) : null}

      {panel === "ledger" ? (
        <div className="table-wrap mt-4" data-testid="movement-ledger">
          <table>
            <thead>
              <tr>
                {["When", "SKU", "Location", "Type", "Quantity", "Reason"].map((heading) => (
                  <th key={heading}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {movements.length === 0 ? (
                <tr>
                  <td colSpan={6}>{loaded ? "No movements yet." : "Loading the ledger…"}</td>
                </tr>
              ) : (
                movements.map((row) => (
                  <tr key={row.id} data-testid="movement-row" data-sku={row.sku} data-type={row.movement_type}>
                    <td className="whitespace-nowrap">{when(row.created_at)}</td>
                    <td className="font-mono text-xs">{row.sku}</td>
                    <td>{row.location_name}</td>
                    <td>{row.movement_type.replace(/_/g, " ")}</td>
                    <td className="font-mono">{formatQty(row.quantity)}</td>
                    <td>{row.reason}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : null}

      {panel === "places" ? (
        <div className="mt-4 space-y-4">
          <form className="flex flex-wrap items-end gap-3" onSubmit={addLocation}>
            <label className="lbl" htmlFor="location-name">
              New location
              <input
                id="location-name"
                data-testid="location-name"
                className="field w-48"
                value={locationName}
                onChange={(event) => setLocationName(event.target.value)}
              />
            </label>
            <label className="lbl" htmlFor="location-kind">
              Kind
              <select
                id="location-kind"
                data-testid="location-kind"
                className="field w-36"
                value={locationKind}
                onChange={(event) => setLocationKind(event.target.value)}
              >
                {KINDS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="btn btn-secondary" data-testid="location-create" disabled={busy}>
              Create location
            </button>
          </form>
          <form className="flex flex-wrap items-end gap-3" onSubmit={addBin}>
            <label className="lbl" htmlFor="bin-location">
              Bin location
              <select
                id="bin-location"
                data-testid="bin-location"
                className="field w-44"
                value={binLocation}
                onChange={(event) => setBinLocation(event.target.value)}
              >
                {locations.map((place) => (
                  <option key={place.id} value={place.id}>
                    {place.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="lbl" htmlFor="bin-code">
              Code
              <input
                id="bin-code"
                data-testid="bin-code"
                className="field w-32 font-mono"
                value={binCode}
                onChange={(event) => setBinCode(event.target.value)}
              />
            </label>
            <label className="lbl" htmlFor="bin-label">
              Label
              <input
                id="bin-label"
                data-testid="bin-label"
                className="field w-40"
                value={binLabel}
                onChange={(event) => setBinLabel(event.target.value)}
              />
            </label>
            <button type="submit" className="btn btn-primary" data-testid="bin-create" disabled={busy}>
              Create bin
            </button>
          </form>
          <ul className="space-y-2">
            {bins.map((bin) => (
              <li key={bin.id} className="panel flex flex-wrap items-center justify-between gap-3 p-3" data-testid="bin-row">
                <div className="min-w-0">
                  <div className="font-mono text-sm">{bin.code}</div>
                  <div className="text-xs text-muted">
                    {bin.location_name}
                    {bin.label ? ` · ${bin.label}` : ""}
                  </div>
                </div>
                <button type="button" className="btn btn-secondary" data-testid="bin-view-qr" disabled={busy} onClick={() => void showLabel(bin.id)}>
                  View QR
                </button>
              </li>
            ))}
          </ul>
          {labelSvg ? (
            <div className="panel p-3" data-testid="bin-qr">
              <div dangerouslySetInnerHTML={{ __html: labelSvg }} />
              <p className="mt-2 break-all font-mono text-xs" data-testid="bin-qr-payload">
                {labelPayload}
              </p>
              <button type="button" className="btn btn-secondary mt-3" data-testid="bin-qr-print" onClick={printLabel}>
                Print label
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
