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
      <div className="mt-4 flex flex-wrap gap-3">
        <label className="lbl" htmlFor="list-budget">
          Budget (USD)
          <input
            id="list-budget"
            data-testid="list-budget"
            type="number"
            className="field w-36"
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
            className="field w-28"
            value={margin}
            onChange={(e) => setMargin(Number(e.target.value))}
          />
        </label>
      </div>
    </AgentWorkbench>
  );
}
