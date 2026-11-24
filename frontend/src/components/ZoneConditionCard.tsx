"use client";

import { FormEvent, useState } from "react";
import { ApiError, acknowledgeExcursion, recordZoneReading, type StorageZone } from "@/lib/api";

function formatMetric(value: number) {
  return Number(value).toFixed(1).replace(/\.0$/, "");
}

export function ZoneConditionCard({ zone, onChanged }: { zone: StorageZone; onChanged?: () => void }) {
  const [temp, setTemp] = useState("");
  const [humidity, setHumidity] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reading = zone.latest_reading;
  const excursion = zone.excursion;
  const open = excursion?.status === "open";
  const alerting = zone.status !== "ok";

  async function record(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await recordZoneReading(zone.id, Number(temp), Number(humidity), note);
      setTemp("");
      setHumidity("");
      setNote("");
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "The reading could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function acknowledge() {
    if (!excursion) return;
    setBusy(true);
    setError("");
    try {
      await acknowledgeExcursion(excursion.id, note);
      setNote("");
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "The excursion could not be acknowledged.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="panel min-w-0 p-3" data-testid="zone-card" data-zone={zone.name}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="break-words text-sm font-medium">{zone.name}</h3>
          {zone.location_name ? <p className="text-xs text-muted">{zone.location_name}</p> : null}
        </div>
        <span className={alerting ? "badge badge-alert" : "badge badge-ok"} data-testid="zone-status">
          {alerting ? "Excursion" : "OK"}
        </span>
      </div>
      <p className="mt-2 break-words text-sm text-muted">
        Target {formatMetric(zone.target_temp_min_c)}–{formatMetric(zone.target_temp_max_c)}°C ·{" "}
        {formatMetric(zone.target_humidity_min_pct)}–{formatMetric(zone.target_humidity_max_pct)}% RH
      </p>
      <p className="mt-1 text-sm" data-testid="zone-reading">
        {reading
          ? `Latest ${formatMetric(reading.temp_c)}°C · ${formatMetric(reading.humidity_pct)}% RH`
          : "No reading yet"}
      </p>
      {alerting && excursion ? (
        <div className="mt-2 min-w-0" data-testid="zone-excursion">
          <p className="text-sm">
            {excursion.metric.replace(/_/g, " ")}
            {open ? "" : " · acknowledged"}
          </p>
          <ul className="mt-1 space-y-1" data-testid="affected-skus">
            {(excursion.affected_skus || []).map((row) => (
              <li key={`${row.bin_code}-${row.sku}`} className="break-words text-sm" data-testid="affected-sku">
                {row.sku} · {row.product_name} · {row.bin_code} · {row.on_hand}
              </li>
            ))}
            {(excursion.affected_skus || []).length === 0 ? <li className="text-sm text-muted">No bottles in this zone.</li> : null}
          </ul>
        </div>
      ) : null}
      <form className="mt-3 grid gap-2" onSubmit={record}>
        <div className="grid grid-cols-2 gap-2">
          <label className="lbl min-w-0" htmlFor={`zone-temp-${zone.id}`}>
            °C
            <input
              id={`zone-temp-${zone.id}`}
              data-testid="zone-temp"
              className="field w-full"
              inputMode="decimal"
              value={temp}
              onChange={(event) => setTemp(event.target.value)}
              required
            />
          </label>
          <label className="lbl min-w-0" htmlFor={`zone-humidity-${zone.id}`}>
            % RH
            <input
              id={`zone-humidity-${zone.id}`}
              data-testid="zone-humidity"
              className="field w-full"
              inputMode="decimal"
              value={humidity}
              onChange={(event) => setHumidity(event.target.value)}
              required
            />
          </label>
        </div>
        <label className="lbl" htmlFor={`zone-note-${zone.id}`}>
          Note
          <input
            id={`zone-note-${zone.id}`}
            data-testid="zone-note"
            className="field w-full"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-primary w-full" data-testid="zone-record" disabled={busy}>
          Log reading
        </button>
      </form>
      {open ? (
        <button
          type="button"
          className="btn btn-secondary mt-2 w-full"
          data-testid="zone-acknowledge"
          disabled={busy}
          onClick={() => void acknowledge()}
        >
          Acknowledge
        </button>
      ) : null}
      {error ? (
        <p className="banner-error mt-2" role="alert" data-testid="zone-error">
          {error}
        </p>
      ) : null}
    </article>
  );
}
