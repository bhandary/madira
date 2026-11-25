"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AgentWorkbench } from "@/components/AgentWorkbench";
import { CellarBoard } from "@/components/CellarBoard";
import { ZoneConditionCard } from "@/components/ZoneConditionCard";
import { getInventory, getSensors, listStorageZones, patchStock, type SensorRecord, type StorageZone } from "@/lib/api";
import { SensorStatusView } from "@/components/SensorViews";

type Item = {
  sku: string;
  name: string;
  on_hand: number;
  par: number;
  low: boolean;
};

export default function InventoryPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [sku, setSku] = useState("W-MUS-01");
  const [qty, setQty] = useState(1);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [zones, setZones] = useState<StorageZone[]>([]);
  const [sensors, setSensors] = useState<SensorRecord[]>([]);

  async function refresh() {
    const data = await getInventory();
    setItems(data.items || []);
    setLoaded(true);
    setError("");
  }

  const refreshZones = useCallback(() => {
    listStorageZones()
      .then((data) => setZones(data.zones || []))
      .catch(() => setZones([]));
    getSensors()
      .then((data) => setSensors(data.sensors || []))
      .catch(() => setSensors([]));
  }, []);

  useEffect(() => {
    refreshZones();
  }, [refreshZones]);

  useEffect(() => {
    let cancelled = false;
    getInventory()
      .then((data) => {
        if (!cancelled) {
          setItems(data.items || []);
          setLoaded(true);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Inventory could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const prompt = `Set on-hand for ${sku} to ${qty}, then draft purchase orders for every SKU below par. Do not transmit orders.`;

  return (
    <AgentWorkbench
      testId="inventory-workbench"
      title="Inventory & purchasing"
      blurb="Adjust stock on the floor, then let Inventory & Purchasing draft supplier POs. Seeded cellar data ships with the demo."
      prompt={prompt}
    >
      <p className="mt-4">
        <Link href="/inventory/count" className="btn btn-primary" data-testid="open-count">
          Count on a phone
        </Link>
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="lbl" htmlFor="inv-sku">
          SKU
          <input
            id="inv-sku"
            data-testid="inv-sku"
            className="field w-36 font-mono"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
          />
        </label>
        <label className="lbl" htmlFor="inv-qty">
          On hand
          <input
            id="inv-qty"
            data-testid="inv-qty"
            type="number"
            className="field w-24"
            value={qty}
            onChange={(e) => setQty(Number(e.target.value))}
          />
        </label>
        <button
          type="button"
          data-testid="inv-adjust"
          className="btn btn-secondary"
          onClick={async () => {
            try {
              await patchStock(sku, qty);
              setRevision((value) => value + 1);
              await refresh();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Stock could not be adjusted.");
            }
          }}
        >
          Adjust stock now
        </button>
      </div>
      {error ? (
        <p className="banner-error mt-3" role="alert" data-testid="inventory-error">
          {error}
        </p>
      ) : (
        <p className="mt-2 text-xs text-muted">
          {loaded ? `${items.filter((i) => i.low).length} SKUs under par in the seeded cellar.` : "Loading cellar…"}
        </p>
      )}
      <CellarBoard
        revision={revision}
        onStockChanged={() => {
          setRevision((value) => value + 1);
          void refresh();
        }}
      />
      <section className="mt-8 min-w-0" aria-labelledby="storage-heading" data-testid="storage-zones">
        <h2 id="storage-heading" className="text-lg font-medium">
          Storage zones
        </h2>
        <p className="mt-1 text-sm text-muted">
          Log a temperature and humidity reading. An out-of-range reading opens an excursion for the bottles in that zone.
        </p>
        <div className="mt-3 min-w-0">
          <SensorStatusView
            sensors={sensors.map((row) => ({
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
            }))}
          />
        </div>
        <div className="mt-3 space-y-3">
          {zones.map((zone) => (
            <ZoneConditionCard key={zone.id} zone={zone} onChanged={refreshZones} />
          ))}
          {loaded && zones.length === 0 ? <p className="text-sm text-muted">No storage zones yet.</p> : null}
        </div>
      </section>
    </AgentWorkbench>
  );
}
