"use client";

import { useState } from "react";
import { ApiError, confirmMenu, updateDishField, type MenuDish, type MenuReview } from "@/lib/api";

const LABELS: Record<string, string> = {
  name: "Name",
  course: "Course",
  price: "Price",
  main_component: "Main component",
  cooking_method: "Cooking method",
  sauce: "Sauce",
  richness: "Richness",
  acidity: "Acidity",
  sweetness: "Sweetness",
  spice: "Spice",
  umami: "Umami",
  allergens: "Allergens",
};

function message(err: unknown, fallback: string) {
  if (err instanceof ApiError && err.message) return err.message;
  return fallback;
}

function money(minor: number, currency: string) {
  const code = /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  return (minor / 100).toLocaleString(undefined, { style: "currency", currency: code });
}

function shown(dish: MenuDish, field: string) {
  if (field === "price") return money(dish.price, dish.currency);
  if (field === "allergens") return dish.allergens.join(", ") || "None";
  const value = dish[field as keyof MenuDish];
  if (value === "" || value === null || value === undefined) return "—";
  return String(value);
}

export function asReview(value: unknown): MenuReview | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Partial<MenuReview>;
  if (typeof row.menu_id !== "string" || typeof row.version_id !== "string" || !Array.isArray(row.dishes)) return null;
  return {
    menu_id: row.menu_id,
    version_id: row.version_id,
    name: String(row.name ?? ""),
    number: Number(row.number ?? 0),
    status: String(row.status ?? "draft"),
    cuisine: String(row.cuisine ?? ""),
    price_tier: String(row.price_tier ?? ""),
    dishes: row.dishes.map((item) => {
      const dish = item as Partial<MenuDish>;
      return {
        id: String(dish.id ?? ""),
        stable_id: String(dish.stable_id ?? ""),
        name: String(dish.name ?? ""),
        course: String(dish.course ?? ""),
        price: Number(dish.price ?? 0),
        currency: String(dish.currency ?? "USD"),
        main_component: String(dish.main_component ?? ""),
        cooking_method: String(dish.cooking_method ?? ""),
        sauce: String(dish.sauce ?? ""),
        richness: Number(dish.richness ?? 0),
        acidity: Number(dish.acidity ?? 0),
        sweetness: Number(dish.sweetness ?? 0),
        spice: Number(dish.spice ?? 0),
        umami: Number(dish.umami ?? 0),
        allergens: Array.isArray(dish.allergens) ? dish.allergens.map(String) : [],
        confidence: dish.confidence && typeof dish.confidence === "object" ? dish.confidence : {},
        low_confidence: Array.isArray(dish.low_confidence) ? dish.low_confidence.map(String) : [],
        needs_repairing: dish.needs_repairing === true,
      };
    }),
  };
}

function DishCard({
  review,
  dish,
  onSaved,
}: {
  review: MenuReview;
  dish: MenuDish;
  onSaved: (review: MenuReview) => void;
}) {
  const flagged = new Set(dish.low_confidence);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const locked = review.status === "confirmed";

  function draftValue(field: string) {
    if (field in drafts) return drafts[field];
    if (field === "allergens") return dish.allergens.join(", ");
    const value = dish[field as keyof MenuDish];
    return value === undefined || value === null ? "" : String(value);
  }

  async function save() {
    const fields = Object.keys(drafts);
    if (!fields.length || busy || locked) return;
    setBusy(true);
    setError("");
    try {
      let next = review;
      for (const field of fields) {
        const raw = drafts[field];
        const value =
          field === "allergens"
            ? raw.split(",").map((part) => part.trim()).filter(Boolean)
            : field === "price" || field === "richness" || field === "acidity" || field === "sweetness" || field === "spice" || field === "umami"
              ? Number(raw)
              : raw;
        const saved = await updateDishField(review.menu_id, review.version_id, dish.id, field, value);
        next = saved.review;
      }
      setDrafts({});
      onSaved(next);
    } catch (err) {
      setError(message(err, "That dish could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="panel min-w-0 p-4" data-testid="dish-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="min-w-0 break-words text-base text-ink" data-testid="dish-name">
          {dish.name}
        </h3>
        {dish.needs_repairing ? (
          <span className="badge badge-draft" data-testid="dish-repair">
            Re-pair
          </span>
        ) : (
          <span className="badge badge-ok">Unchanged</span>
        )}
      </div>
      <p className="mt-1 text-sm text-muted">
        {dish.course || "Course"} · {money(dish.price, dish.currency)}
      </p>
      <div className="mt-3 grid gap-3">
        {Object.keys(LABELS).map((field) => {
          const low = flagged.has(field);
          if (!low) {
            return (
              <p key={field} className="text-sm text-ink" data-testid={`dish-value-${field}`}>
                <span className="text-muted">{LABELS[field]}: </span>
                {shown(dish, field)}
              </p>
            );
          }
          return (
            <label key={field} className="lbl" htmlFor={`${dish.id}-${field}`}>
              <span className="flex flex-wrap items-center gap-2">
                {LABELS[field]}
                <span className="badge badge-alert" data-testid="dish-flag">
                  Low confidence
                </span>
              </span>
              <input
                id={`${dish.id}-${field}`}
                data-testid={`dish-field-${field}`}
                className="field"
                value={draftValue(field)}
                disabled={locked || busy}
                onChange={(event) => setDrafts({ ...drafts, [field]: event.target.value })}
              />
            </label>
          );
        })}
      </div>
      {error && (
        <p className="banner-error mt-3" role="alert">
          {error}
        </p>
      )}
      {!locked && flagged.size > 0 && (
        <button type="button" className="btn btn-secondary mt-3 w-full" data-testid="dish-save" disabled={busy} onClick={() => void save()}>
          {busy ? "Saving…" : "Save field"}
        </button>
      )}
    </article>
  );
}

export function DishReview({ review, onChange }: { review: MenuReview; onChange?: (review: MenuReview) => void }) {
  const [current, setCurrent] = useState(review);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const confirmed = current.status === "confirmed";

  function apply(next: MenuReview) {
    setCurrent(next);
    onChange?.(next);
  }

  async function confirm() {
    if (busy || confirmed) return;
    setBusy(true);
    setError("");
    try {
      const saved = await confirmMenu(current.menu_id, current.version_id);
      apply(saved.review);
    } catch (err) {
      setError(message(err, "This menu could not be confirmed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-4 min-w-0" data-testid="dish-review">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="min-w-0 break-words text-lg text-ink">{current.name}</h2>
        <span className={confirmed ? "badge badge-ok" : "badge badge-draft"} data-testid="dish-review-status">
          {confirmed ? "Confirmed" : "Draft"}
        </span>
      </div>
      <p className="mt-1 text-sm text-muted">
        Version {current.number}. Low-confidence fields are flagged. Confirm the menu before pairing uses it.
      </p>
      <div className="mt-3 grid gap-3">
        {current.dishes.map((dish) => (
          <DishCard key={dish.id} review={current} dish={dish} onSaved={apply} />
        ))}
      </div>
      {error && (
        <p className="banner-error mt-3" role="alert" data-testid="dish-review-error">
          {error}
        </p>
      )}
      <button
        type="button"
        className="btn btn-primary mt-3 w-full"
        data-testid="dish-confirm"
        disabled={busy || confirmed}
        onClick={() => void confirm()}
      >
        {confirmed ? "Confirmed" : busy ? "Confirming…" : "Confirm menu"}
      </button>
    </section>
  );
}
