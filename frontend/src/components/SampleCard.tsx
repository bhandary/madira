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
  const [quote, setQuote] = useState(sample.quoted_price_cents == null ? "" : String(sample.quoted_price_cents));
  const [reason, setReason] = useState(sample.pass_reason || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function apply(next: SampleCardData) {
    setRow(next);
    setScore(next.score == null ? "" : String(next.score));
    setQuote(next.quoted_price_cents == null ? "" : String(next.quoted_price_cents));
    setReason(next.pass_reason || "");
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

      <div className="flex flex-wrap items-end gap-2">
        <label className="block min-w-0 flex-1 text-sm">
          Quoted price (cents)
          <input
            className="field mt-1 min-h-11 w-full"
            data-testid="sample-quote"
            inputMode="numeric"
            value={quote}
            disabled={busy}
            onChange={(event) => setQuote(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn min-h-11"
          data-testid="sample-quote-save"
          disabled={busy}
          onClick={() => {
            const parsed = quote.trim() === "" ? null : Number(quote);
            void run(async () => (await updateSample(row.session_id, row.id, { quoted_price_cents: parsed })).sample);
          }}
        >
          Save price
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <button
          type="button"
          className="btn btn-primary min-h-11"
          data-testid="sample-buy"
          disabled={busy}
          onClick={() => void run(async () => (await setSampleDecision(row.session_id, row.id, "buy")).sample)}
        >
          Buy
        </button>
        <button
          type="button"
          className="btn min-h-11"
          data-testid="sample-list"
          disabled={busy}
          onClick={() => void run(async () => (await setSampleDecision(row.session_id, row.id, "list")).sample)}
        >
          List
        </button>
        <button
          type="button"
          className="btn min-h-11"
          data-testid="sample-pass"
          disabled={busy || reason.trim() === ""}
          onClick={() => void run(async () => (await setSampleDecision(row.session_id, row.id, "pass", reason.trim())).sample)}
        >
          Pass
        </button>
      </div>
      <label className="block text-sm">
        Pass reason
        <input
          className="field mt-1 min-h-11 w-full"
          data-testid="sample-pass-reason"
          value={reason}
          disabled={busy}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      {row.purchase_order_id ? (
        <a className="btn inline-flex min-h-11 items-center" data-testid="sample-po" data-po={row.purchase_order_number} href="/purchasing">
          Draft {row.purchase_order_number || "purchase order"}
        </a>
      ) : null}
      {row.list_version_id ? (
        <a className="btn inline-flex min-h-11 items-center" data-testid="sample-list-link" href="/list">
          Draft list v{row.list_version_number ?? ""}
        </a>
      ) : null}
      {row.decision === "pass" && row.pass_reason ? (
        <p className="text-sm" data-testid="sample-passed">
          Passed: {row.pass_reason}
        </p>
      ) : null}
      {row.note ? <p className="text-sm text-muted">{row.note}</p> : null}
      {error ? <p className="text-sm text-alert">{error}</p> : null}
    </article>
  );
}
