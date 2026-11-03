"use client";

import { useState } from "react";
import { AgentWorkbench } from "@/components/AgentWorkbench";

export default function ListPage() {
  const [budget, setBudget] = useState(12000);
  const [margin, setMargin] = useState(3.2);
  const prompt = `Curate a wine, beer, spirit, and sake list to complement the Maison Madira autumn menu. Budget $${budget}. Target pour/bottle margin ${margin}x. Show coverage by category/region/style/price, gaps, and cost/margin math.`;

  return (
    <AgentWorkbench
      testId="list-workbench"
      title="List curation"
      blurb="List Curator buys to a cellar budget and a target multiple. Coverage and gaps render as an A2UI table."
      prompt={prompt}
    >
      <div className="mt-4 flex flex-wrap gap-4">
        <label className="text-sm">
          Budget (USD)
          <input
            data-testid="list-budget"
            type="number"
            className="ml-2 w-28 rounded-lg border border-gold/40 bg-white px-2 py-1"
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </label>
        <label className="text-sm">
          Target multiple
          <input
            data-testid="list-margin"
            type="number"
            step="0.1"
            className="ml-2 w-20 rounded-lg border border-gold/40 bg-white px-2 py-1"
            value={margin}
            onChange={(e) => setMargin(Number(e.target.value))}
          />
        </label>
      </div>
    </AgentWorkbench>
  );
}
