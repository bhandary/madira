"use client";

import { FormEvent, useEffect, useState } from "react";
import { sensorStatusItem } from "@/a2ui/sensorSchema";
import { SensorStatusView } from "@/components/SensorViews";
import {
  ApiError,
  applySensorImport,
  createSensor,
  getSensors,
  listStorageZones,
  previewSensorCsv,
  rejectSensorImport,
  type SensorImport,
  type SensorRecord,
  type StorageZone,
} from "@/lib/api";

function message(err: unknown) {
  return err instanceof ApiError ? err.message : "The sensor desk could not be updated.";
}

export default function SensorsPage() {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [zones, setZones] = useState<StorageZone[]>([]);
  const [sensors, setSensors] = useState<SensorRecord[]>([]);
  const [name, setName] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [metric, setMetric] = useState("temperature_c");
  const [externalId, setExternalId] = useState("");
  const [secret, setSecret] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SensorImport | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listStorageZones(), getSensors()])
      .then(([zonePayload, sensorPayload]) => {
        if (cancelled) return;
        const nextZones = zonePayload.zones || [];
        setZones(nextZones);
        setZoneId((current) => current || nextZones[0]?.id || "");
        const parsed = sensorStatusItem.array().safeParse(
          (sensorPayload.sensors || []).map((row) => ({
            id: row.id,
            name: row.name,
            zone_name: row.zone_name,
            location_name: row.location_name,
            metric: row.metric,
            external_id: row.external_id,
            masked: row.masked,
            last_value: row.last_value,
            last_at: row.last_at,
            stale: row.stale,
            stale_after_hours: row.stale_after_hours,
          })),
        );
        setSensors(sensorPayload.sensors || []);
        if (!parsed.success) setError("Sensor status could not be read.");
        setReady(true);
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(message(exc));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshSensors() {
    const payload = await getSensors();
    setSensors(payload.sensors || []);
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSecret("");
    try {
      const created = await createSensor({ name, zone_id: zoneId, metric, external_id: externalId });
      setSecret(created.secret || "");
      setName("");
      setExternalId("");
      await refreshSensors();
    } catch (exc) {
      setError(message(exc));
    } finally {
      setBusy(false);
    }
  }

  async function onPreview() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setPreview(await previewSensorCsv(file));
    } catch (exc) {
      setError(message(exc));
    } finally {
      setBusy(false);
    }
  }

  async function onApply() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const applied = await applySensorImport(preview.id);
      setPreview(applied);
      await refreshSensors();
    } catch (exc) {
      setError(message(exc));
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      setPreview(await rejectSensorImport(preview.id));
    } catch (exc) {
      setError(message(exc));
    } finally {
      setBusy(false);
    }
  }

  const cards = sensors.map((row) => ({
    id: row.id,
    name: row.name,
    zone_name: row.zone_name,
    location_name: row.location_name,
    metric: row.metric,
    external_id: row.external_id,
    masked: row.masked,
    last_value: row.last_value,
    last_at: row.last_at,
    stale: row.stale,
    stale_after_hours: row.stale_after_hours,
  }));

  return (
    <div className="mx-auto w-full max-w-lg min-w-0 space-y-6">
      <header>
        <h1 className="h-page">Sensors</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          A signed webhook or a reviewed CSV posts readings to the cellar. The signing secret is shown once.
        </p>
      </header>
      {error ? (
        <p className="text-sm" role="alert">
          {error}
        </p>
      ) : null}
      <section className="panel min-w-0" data-testid="sensor-register">
        <h2 className="text-base font-semibold">Register</h2>
        <form className="mt-3 grid min-w-0 gap-3" onSubmit={onCreate}>
          <label className="lbl min-w-0" htmlFor="sensor-name">
            Name
            <input id="sensor-name" className="field w-full" value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label className="lbl min-w-0" htmlFor="sensor-zone">
            Storage zone
            <select
              id="sensor-zone"
              className="field w-full max-w-full"
              data-testid="sensor-zone"
              value={zoneId}
              onChange={(event) => setZoneId(event.target.value)}
              required
            >
              {zones.map((zone) => (
                <option key={zone.id} value={zone.id}>
                  {zone.name}
                </option>
              ))}
            </select>
          </label>
          <label className="lbl min-w-0" htmlFor="sensor-metric">
            Metric
            <select
              id="sensor-metric"
              className="field w-full max-w-full"
              data-testid="sensor-metric"
              value={metric}
              onChange={(event) => setMetric(event.target.value)}
            >
              <option value="temperature_c">Temperature °C</option>
              <option value="humidity_pct">Humidity %</option>
            </select>
          </label>
          <label className="lbl min-w-0" htmlFor="sensor-external">
            External id
            <input
              id="sensor-external"
              className="field w-full"
              data-testid="sensor-external"
              value={externalId}
              onChange={(event) => setExternalId(event.target.value)}
              required
            />
          </label>
          <button className="btn min-h-11 w-full whitespace-normal" type="submit" data-testid="sensor-create" disabled={!ready || busy || !zoneId}>
            Register sensor
          </button>
        </form>
        {secret ? (
          <p className="mt-3 break-all text-sm" data-testid="sensor-secret">
            Signing secret {secret}. Copy it now. Later requests show only the last four characters.
          </p>
        ) : null}
      </section>
      <section className="panel min-w-0">
        <h2 className="text-base font-semibold">Status</h2>
        <div className="mt-2">
          <SensorStatusView sensors={cards} />
        </div>
        <ul className="mt-3 space-y-1 text-sm text-[var(--muted)]">
          {sensors.map((sensor) => (
            <li key={sensor.id} className="break-all">
              {sensor.name} · secret {sensor.masked}
            </li>
          ))}
        </ul>
      </section>
      <section className="panel min-w-0" data-testid="sensor-import">
        <h2 className="text-base font-semibold">CSV import</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">Columns: sensor or external id, timestamp, metric, value. Preview before apply.</p>
        <label className="lbl mt-3 min-w-0" htmlFor="sensor-csv">
          File
          <input
            id="sensor-csv"
            className="field w-full max-w-full"
            data-testid="sensor-csv"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null);
              setPreview(null);
            }}
          />
        </label>
        <div className="mt-3 grid gap-2">
          <button className="btn min-h-11 w-full whitespace-normal" type="button" data-testid="sensor-preview" disabled={!ready || busy || !file} onClick={() => void onPreview()}>
            Preview CSV
          </button>
          {preview && preview.status === "pending_review" ? (
            <>
              <button className="btn min-h-11 w-full whitespace-normal" type="button" data-testid="sensor-apply" disabled={busy} onClick={() => void onApply()}>
                Apply import
              </button>
              <button className="btn btn-secondary min-h-11 w-full whitespace-normal" type="button" data-testid="sensor-reject" disabled={busy} onClick={() => void onReject()}>
                Reject import
              </button>
            </>
          ) : null}
        </div>
        {preview ? (
          <ul className="mt-3 space-y-2" data-testid="sensor-preview-rows">
            {preview.rows.map((row) => (
              <li key={row.line} className="min-w-0 break-words text-sm" data-testid="sensor-preview-row">
                {row.external_id || row.sensor} · {row.value} · {row.excursion ? `excursion ${row.excursion}` : row.error || "in range"}
                {row.duplicate ? " · duplicate" : ""}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
