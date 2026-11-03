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

  async function refresh() {
    const data = await getInventory();
    setItems(data.items || []);
  }

  useEffect(() => {
    let cancelled = false;
    getInventory()
      .then((data) => {
        if (!cancelled) setItems(data.items || []);
      })
      .catch(() => undefined);
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
        <label className="text-sm">
          SKU
          <input
            data-testid="inv-sku"
            className="ml-2 w-28 rounded-lg border border-gold/40 bg-white px-2 py-1 font-mono"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
          />
        </label>
        <label className="text-sm">
          On hand
          <input
            data-testid="inv-qty"
            type="number"
            className="ml-2 w-20 rounded-lg border border-gold/40 bg-white px-2 py-1"
            value={qty}
            onChange={(e) => setQty(Number(e.target.value))}
          />
        </label>
        <button
          type="button"
          data-testid="inv-adjust"
          className="rounded-full border border-burgundy px-3 py-1 text-sm"
          onClick={async () => {
            await patchStock(sku, qty);
            await refresh();
          }}
        >
          Adjust stock now
        </button>
      </div>
      <p className="mt-2 text-xs text-[#7a6a58]">
        {items.filter((i) => i.low).length} SKUs under par in the seeded cellar.
      </p>
    </AgentWorkbench>
  );
}
