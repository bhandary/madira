"use client";

import { useEffect, useState } from "react";
import { AgentWorkbench } from "@/components/AgentWorkbench";
import { CoverageGrid } from "@/components/CoverageGrid";
import { ListEditor } from "@/components/ListEditor";
import { ListImport } from "@/components/ListImport";
import { ApiError, curateList, getLists, type BeverageListDetail, type HealthFlag } from "@/lib/api";

function money(minor: number, currency: string) {
  const code = /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  return (minor / 100).toLocaleString(undefined, { style: "currency", currency: code });
}

function flagLabel(flag: HealthFlag) {
  return {
    dish_unpaired: "Unpaired dish",
    item_unpaired: "Unpaired bottle",
    slow_mover: "Slow mover",
    price_outlier: "Price",
    section_over: "Section over",
    section_under: "Section under",
    drink_window: "Drink window",
  }[flag.code] || flag.code;
}

export default function ListPage() {
  const [budget, setBudget] = useState(12000);
  const [margin, setMargin] = useState(3.2);
  const [targetCost, setTargetCost] = useState(31.3);
  const [concept, setConcept] = useState("");
  const [priceTier, setPriceTier] = useState("");
  const [lists, setLists] = useState<BeverageListDetail[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [deskReady, setDeskReady] = useState(false);
  const prompt = `Curate a wine, beer, spirit, and sake list to complement the Maison Madira autumn menu. Budget $${budget}. Target pour/bottle margin ${margin}x. Show coverage by category/region/style/price, gaps, and cost/margin math.`;
  const selected = lists.find((row) => row.list_id === selectedId) || null;

  useEffect(() => {
    let live = true;
    getLists()
      .then((body) => {
        if (!live) return;
        setLists((current) => (current.length > 0 ? current : body.lists));
        setSelectedId((current) => current || body.lists[0]?.list_id || "");
      })
      .catch(() => {
        if (live) setError("The lists could not be loaded.");
      })
      .finally(() => {
        if (live) setDeskReady(true);
      });
    return () => {
      live = false;
    };
  }, []);

  function remember(list: BeverageListDetail) {
    setLists((current) => [list, ...current.filter((row) => row.list_id !== list.list_id)]);
    setSelectedId(list.list_id);
  }

  async function curate() {
    setBusy(true);
    setError("");
    try {
      remember(
        await curateList({
          budget,
          target_margin: margin,
          target_beverage_cost_pct: targetCost,
          concept,
          price_tier: priceTier,
          name: "Maison Madira autumn list",
        }),
      );
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The list could not be curated.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AgentWorkbench
      testId="list-workbench"
      title="List curation"
      blurb="The list curator builds from the confirmed menu, the budget, and cellar capacity. Prices, margins, and health come from the list service."
      prompt={prompt}
    >
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="lbl" htmlFor="list-budget">
          Budget (USD)
          <input
            id="list-budget"
            data-testid="list-budget"
            type="number"
            className="field min-h-11 w-full"
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </label>
        <label className="lbl" htmlFor="list-margin">
          Target multiple
          <input
            id="list-margin"
            data-testid="list-margin"
            type="number"
            step="0.1"
            className="field min-h-11 w-full"
            value={margin}
            onChange={(e) => setMargin(Number(e.target.value))}
          />
        </label>
        <label className="lbl" htmlFor="list-target-cost">
          Target beverage cost %
          <input
            id="list-target-cost"
            data-testid="list-target-cost"
            type="number"
            step="0.1"
            className="field min-h-11 w-full"
            value={targetCost}
            onChange={(e) => setTargetCost(Number(e.target.value))}
          />
        </label>
        <label className="lbl" htmlFor="list-price-tier">
          Price tier
          <input
            id="list-price-tier"
            data-testid="list-price-tier"
            className="field min-h-11 w-full"
            value={priceTier}
            onChange={(e) => setPriceTier(e.target.value)}
          />
        </label>
        <label className="lbl sm:col-span-2" htmlFor="list-concept">
          Concept
          <input
            id="list-concept"
            data-testid="list-concept"
            className="field min-h-11 w-full"
            value={concept}
            onChange={(e) => setConcept(e.target.value)}
          />
        </label>
      </div>
      <button
        type="button"
        className="btn btn-primary mt-3 min-h-11"
        data-testid="list-curate"
        disabled={busy || !deskReady}
        onClick={() => void curate()}
      >
        {busy ? "Curating…" : "Curate from menu"}
      </button>
      {error && (
        <p className="banner-error mt-3" role="alert">
          {error}
        </p>
      )}
      <div className="mt-5 min-w-0">
        <label className="lbl" htmlFor="list-picker">
          List
          <select
            id="list-picker"
            data-testid="list-picker"
            className="field min-h-11 w-full"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            <option value="">No list yet</option>
            {lists.map((row) => (
              <option key={row.list_id} value={row.list_id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {selected && (
        <div className="mt-4 grid min-w-0 gap-4">
          <div className="panel p-3 text-sm" data-testid="list-spend">
            Spent {money(selected.spent, selected.currency)} of {money(selected.budget, selected.currency)}
            {selected.capacity_bottles != null ? ` · ${selected.bottles} of ${selected.capacity_bottles} bottles` : ""}
          </div>
          <ListEditor
            listId={selected.list_id}
            currency={selected.currency}
            sections={selected.sections}
            items={selected.items}
            candidates={selected.candidates}
            onChanged={remember}
          />
          <section data-testid="list-health">
            <h3 className="text-base text-ink">Health</h3>
            {selected.health.flags.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No health flags.</p>
            ) : (
              <ul className="mt-2 grid gap-2">
                {selected.health.flags.map((flag, index) => (
                  <li key={`${flag.code}-${flag.item_id || flag.dish_id || index}`} className="panel p-3 text-sm" data-testid="list-health-flag">
                    <span className="badge">{flagLabel(flag)}</span>
                    <span className="mt-1 block text-ink">{flag.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <CoverageGrid cells={selected.cells} />
        </div>
      )}
      <ListImport />
    </AgentWorkbench>
  );
}
