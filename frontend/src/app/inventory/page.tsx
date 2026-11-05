"use client";

import { useEffect, useState } from "react";
import { AgentWorkbench } from "@/components/AgentWorkbench";
import { getInventory, patchStock } from "@/lib/api";

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

  async function refresh() {
    const data = await getInventory();
    setItems(data.items || []);
    setLoaded(true);
    setError("");
  }

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
    </AgentWorkbench>
  );
}
