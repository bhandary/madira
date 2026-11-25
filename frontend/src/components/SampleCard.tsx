"use client";

import { useState } from "react";
import type { SampleCardData, SampleProductOption } from "@/a2ui/sampleCardSchema";
import {
  ApiError,
  scanSampleLabel,
  scoreSample,
  setSampleDecision,
  updateSample,
} from "@/lib/api";

const DECISIONS = [
  ["undecided", "Undecided"],
  ["buy", "Buy"],
  ["list", "List"],
  ["pass", "Pass"],
] as const;

export function SampleCard({
  sample,
  products = [],
  onChange,
}: {
  sample: SampleCardData;
  products?: SampleProductOption[];
  onChange?: (sample: SampleCardData) => void;
}) {
  const [row, setRow] = useState(sample);
  const [score, setScore] = useState(sample.score == null ? "" : String(sample.score));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function apply(next: SampleCardData) {
    setRow(next);
    setScore(next.score == null ? "" : String(next.score));
    onChange?.(next);
  }

  async function run(work: () => Promise<SampleCardData>) {
    setBusy(true);
    setError("");
    try {
      apply(await work());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The sample could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const price = row.list_price;
  const pairs = row.pairs_with;

  return (
    <article className="panel space-y-3 p-3" data-testid="sample-card">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-base font-medium">{row.product_name || "Unmatched sample"}</h3>
        <p className="text-sm text-muted" data-testid="sample-score-value">
          {row.score == null ? "No score" : `Score ${row.score}`}
        </p>
      </div>

      <label className="block text-sm">
        Label photo
        <input
          className="field mt-1 min-h-11 w-full"
          data-testid="sample-label"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            void run(async () => (await scanSampleLabel(row.session_id, row.id, file)).sample);
          }}
        />
      </label>

      {!row.matched ? (
        <label className="block text-sm">
          Catalog product
          <select
            className="field mt-1 min-h-11 w-full"
            data-testid="sample-product"
            value={row.product_id || ""}
            disabled={busy}
            onChange={(event) => {
              const productId = event.target.value;
              if (!productId) return;
              void run(async () => (await updateSample(row.session_id, row.id, { product_id: productId })).sample);
            }}
          >
            <option value="">Unmatched</option>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div className="flex flex-wrap items-end gap-2">
        <label className="block min-w-0 flex-1 text-sm">
          Score
          <input
            className="field mt-1 min-h-11 w-full"
            data-testid="sample-score"
            inputMode="numeric"
            min={0}
            max={100}
            value={score}
            disabled={busy}
            onChange={(event) => setScore(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn btn-primary min-h-11"
          data-testid="sample-score-save"
          disabled={busy}
          onClick={() => {
            const parsed = score.trim() === "" ? null : Number(score);
            void run(async () => (await scoreSample(row.session_id, row.id, parsed)).sample);
          }}
        >
          Save score
        </button>
      </div>

      <p className="text-sm" data-testid="sample-bottle">
        {price.bottle_label ? `Bottle ${price.bottle_label}` : price.note}
      </p>
      <p className="text-sm" data-testid="sample-glass">
        {price.glass_label ? `Glass ${price.glass_label}` : ""}
      </p>
      <p className="text-sm" data-testid="sample-margin">
        {price.margin_label ? `Margin ${price.margin_label}` : ""}
      </p>

      <div data-testid="sample-pairs">
        <p className="text-sm font-medium">Pairs with</p>
        {pairs.note ? <p className="text-sm text-muted">{pairs.note}</p> : null}
        {pairs.dishes.length ? (
          <ul className="mt-1 space-y-1 text-sm">
            {pairs.dishes.map((dish) => (
              <li key={dish.dish_id}>
                {dish.name}
                {dish.course ? ` · ${dish.course}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <label className="block text-sm">
        Decision
        <select
          className="field mt-1 min-h-11 w-full"
          data-testid="sample-decision"
          value={row.decision}
          disabled={busy}
          onChange={(event) => {
            const decision = event.target.value as SampleCardData["decision"];
            void run(async () => (await setSampleDecision(row.session_id, row.id, decision)).sample);
          }}
        >
          {DECISIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {row.note ? <p className="text-sm text-muted">{row.note}</p> : null}
      {error ? <p className="text-sm text-alert">{error}</p> : null}
    </article>
  );
}
