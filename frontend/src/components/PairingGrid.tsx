"use client";

import { useState } from "react";
import { pairingDish, type PairingDish, type PairingSlot } from "@/a2ui/pairingGridSchema";
import { ApiError, pinPairing, rejectPairing, swapPairing } from "@/lib/api";

const STATUS: Record<string, string> = {
  suggested: "Suggested",
  pinned: "Pinned",
  swapped: "Swapped",
  rejected: "Rejected",
  gap: "List gap",
};

function money(amount: number, currency: string) {
  const code = /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  return (amount / 100).toLocaleString(undefined, { style: "currency", currency: code, maximumFractionDigits: 0 });
}

export function asPairings(menuId: unknown, dishes: unknown): { menuId: string; dishes: PairingDish[] } | null {
  const parsed = pairingDish.array().safeParse(dishes);
  if (!parsed.success) return null;
  return { menuId: typeof menuId === "string" ? menuId : "", dishes: parsed.data };
}

export function PairingGrid({ menuId, dishes: initial }: { menuId: string; dishes: PairingDish[] }) {
  const [dishes, setDishes] = useState(initial);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function run(pairingId: string, action: () => Promise<{ dishes: PairingDish[] }>) {
    if (!menuId || busy) return;
    setBusy(pairingId);
    setError("");
    try {
      const next = await action();
      setDishes(next.dishes);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The pairing could not be saved.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="grid min-w-0 gap-3" data-testid="pairing-grid">
      {error && (
        <p className="banner-error" role="alert">
          {error}
        </p>
      )}
      {dishes.map((dish) => (
        <article key={dish.id} className="panel min-w-0 p-3" data-testid="pairing-card">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="min-w-0 break-words text-sm font-medium">{dish.dish || dish.name}</h3>
            <span className="badge badge-wine">{dish.course}</span>
          </div>
          <p className="mt-1 text-sm text-muted">
            Flavor profile: {dish.flavor_profile}
            {dish.price ? ` · ${money(dish.price, dish.currency)}` : ""}
          </p>
          <div className="mt-3 grid gap-2">
            {dish.pairings.map((pairing) => (
              <SlotCard
                key={pairing.id}
                dish={dish}
                pairing={pairing}
                selected={choice[pairing.id] || ""}
                busy={busy === pairing.id}
                locked={!menuId || busy !== ""}
                onSelect={(skuId) => setChoice({ ...choice, [pairing.id]: skuId })}
                onPin={() => void run(pairing.id, () => pinPairing(menuId, pairing.id))}
                onReject={() => void run(pairing.id, () => rejectPairing(menuId, pairing.id))}
                onSwap={() => {
                  const skuId = choice[pairing.id];
                  if (!skuId) return;
                  void run(pairing.id, () => swapPairing(menuId, pairing.id, skuId));
                }}
              />
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function SlotCard({
  dish,
  pairing,
  selected,
  busy,
  locked,
  onSelect,
  onPin,
  onReject,
  onSwap,
}: {
  dish: PairingDish;
  pairing: PairingSlot;
  selected: string;
  busy: boolean;
  locked: boolean;
  onSelect: (skuId: string) => void;
  onPin: () => void;
  onReject: () => void;
  onSwap: () => void;
}) {
  const gap = pairing.status === "gap" || !pairing.sku_id;
  const options = dish.options.filter((option) => option.sku_id !== pairing.sku_id);
  return (
    <div className="min-w-0 rounded-md bg-panel-2 p-3" data-testid={`pairing-slot-${pairing.slot}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="badge badge-draft" data-testid="pairing-status">
          {STATUS[pairing.status] || pairing.status}
        </span>
        <span className="text-xs text-muted">{pairing.confidence}</span>
      </div>
      <div className="mt-1 break-words text-sm font-medium" data-testid="pairing-name">
        {gap ? "No listed bottle" : pairing.name}
      </div>
      {!gap && (
        <div className="break-words text-xs text-muted">
          {[pairing.producer, pairing.region, pairing.style].filter(Boolean).join(" · ")}
        </div>
      )}
      {pairing.rationale && (
        <p className="mt-2 break-words text-sm leading-5" data-testid="pairing-rationale">
          {pairing.rationale}
        </p>
      )}
      {pairing.server_script && (
        <p className="mt-1 break-words text-xs text-muted" data-testid="pairing-script">
          {pairing.server_script}
        </p>
      )}
      {pairing.gap && (
        <p className="mt-2 break-words text-sm" data-testid="pairing-gap">
          {pairing.gap}
        </p>
      )}
      {!gap && (pairing.glass_price > 0 || pairing.bottle_price > 0) && (
        <div className="mt-2 text-xs text-muted">
          {pairing.glass_price > 0 ? `Glass ${money(pairing.glass_price, pairing.currency)}` : ""}
          {pairing.bottle_price > 0 ? `${pairing.glass_price > 0 ? " · " : ""}Bottle ${money(pairing.bottle_price, pairing.currency)}` : ""}
        </div>
      )}
      {!gap && (
        <div className="mt-3 grid gap-2">
          <button type="button" className="btn btn-secondary w-full" data-testid="pairing-pin" disabled={locked} onClick={onPin}>
            {busy ? "Saving…" : "Pin"}
          </button>
          <label className="lbl">
            Swap to a listed bottle
            <select
              className="field"
              data-testid="pairing-swap-select"
              value={selected}
              disabled={locked || options.length === 0}
              onChange={(event) => onSelect(event.target.value)}
            >
              <option value="">Choose a listed bottle</option>
              {options.map((option) => (
                <option key={option.sku_id} value={option.sku_id}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-secondary w-full"
            data-testid="pairing-swap"
            disabled={locked || !selected}
            onClick={onSwap}
          >
            Swap
          </button>
          <button type="button" className="btn btn-secondary w-full" data-testid="pairing-reject" disabled={locked} onClick={onReject}>
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
