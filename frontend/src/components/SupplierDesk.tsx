"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  applyPriceSheet,
  createAllocation,
  deleteAllocation,
  getPriceHistory,
  getSupplierDesk,
  listProcurementSuppliers,
  rejectPriceSheet,
  saveSupplierProfile,
  uploadPriceSheet,
  type AllocationRecord,
  type OfferRecord,
  type PricePointRecord,
  type PriceSheetRecord,
  type SupplierProfile,
  type SupplierRow,
} from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function SupplierDesk() {
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [profile, setProfile] = useState<SupplierProfile | null>(null);
  const [allocations, setAllocations] = useState<AllocationRecord[]>([]);
  const [offers, setOffers] = useState<OfferRecord[]>([]);
  const [products, setProducts] = useState<{ product_id: string; name: string; barcode: string }[]>([]);
  const [sheet, setSheet] = useState<PriceSheetRecord | null>(null);
  const [historyProduct, setHistoryProduct] = useState("");
  const [historyName, setHistoryName] = useState("");
  const [points, setPoints] = useState<PricePointRecord[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [repName, setRepName] = useState("");
  const [repEmail, setRepEmail] = useState("");
  const [repPhone, setRepPhone] = useState("");
  const [days, setDays] = useState<string[]>([]);
  const [minimum, setMinimum] = useState("0");
  const [currency, setCurrency] = useState("USD");
  const [minimumLabel, setMinimumLabel] = useState("");
  const [terms, setTerms] = useState("");
  const [notes, setNotes] = useState("");

  const [allocProduct, setAllocProduct] = useState("");
  const [allocQty, setAllocQty] = useState("1");
  const [allocLabel, setAllocLabel] = useState("");
  const [allocStart, setAllocStart] = useState("");
  const [allocEnd, setAllocEnd] = useState("");

  useEffect(() => {
    let cancelled = false;
    listProcurementSuppliers()
      .then((payload) => {
        if (cancelled) return;
        setSuppliers(payload.suppliers);
        setSupplierId((current) => current || payload.suppliers[0]?.id || "");
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : "Suppliers could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!supplierId) return;
    let cancelled = false;
    getSupplierDesk(supplierId)
      .then((desk) => {
        if (cancelled) return;
        applyDesk(desk);
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof ApiError ? exc.message : "This supplier could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [supplierId]);

  function applyDesk(desk: Awaited<ReturnType<typeof getSupplierDesk>>) {
    const row = desk.supplier;
    setProfile(row);
    setRepName(row.rep_name || "");
    setRepEmail(row.rep_email || "");
    setRepPhone(row.rep_phone || "");
    setDays(row.delivery_days || []);
    setMinimum(String(row.order_minimum_cents ?? 0));
    setCurrency(row.order_minimum_currency || "USD");
    setMinimumLabel(row.order_minimum_label || "");
    setTerms(row.payment_terms || "");
    setNotes(row.notes || "");
    setAllocations(desk.allocations);
    setOffers(desk.current_offers);
    const seen = new Set<string>();
    const choices = desk.products.filter((row) => {
      if (seen.has(row.product_id)) return false;
      seen.add(row.product_id);
      return true;
    });
    setProducts(choices);
    setAllocProduct((current) => current || choices[0]?.product_id || "");
    const pending = desk.price_sheets.find((item) => item.status === "pending_review");
    setSheet((current) => current && current.supplier_id === row.id ? current : pending || null);
  }

  async function refresh(nextProduct?: string) {
    if (!supplierId) return;
    const desk = await getSupplierDesk(supplierId);
    applyDesk(desk);
    const productId = nextProduct || historyProduct;
    if (productId) {
      const history = await getPriceHistory(productId);
      setHistoryProduct(productId);
      setHistoryName(history.product.name);
      setPoints(history.points);
    }
  }

  function toggleDay(day: string) {
    setDays((current) => (current.includes(day) ? current.filter((item) => item !== day) : [...current, day]));
  }

  async function onProfile(event: FormEvent) {
    event.preventDefault();
    if (!supplierId) return;
    setBusy(true);
    setError("");
    try {
      await saveSupplierProfile(supplierId, {
        rep_name: repName,
        rep_email: repEmail,
        rep_phone: repPhone,
        delivery_days: days,
        order_minimum_cents: Number(minimum || 0),
        order_minimum_currency: currency,
        payment_terms: terms,
        notes,
      });
      await refresh();
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The profile could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function onAllocation(event: FormEvent) {
    event.preventDefault();
    if (!supplierId || !allocProduct) return;
    setBusy(true);
    setError("");
    try {
      await createAllocation(supplierId, {
        product_id: allocProduct,
        quantity: Number(allocQty || 0),
        period_label: allocLabel,
        period_start: allocStart || undefined,
        period_end: allocEnd || undefined,
      });
      setAllocLabel("");
      await refresh();
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The allocation could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!supplierId || !file) return;
    setBusy(true);
    setError("");
    try {
      const uploaded = await uploadPriceSheet(supplierId, file);
      setSheet(uploaded.price_sheet);
      setFile(null);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The price sheet could not be read.");
    } finally {
      setBusy(false);
    }
  }

  async function onApply() {
    if (!sheet) return;
    setBusy(true);
    setError("");
    try {
      const applied = await applyPriceSheet(sheet.id);
      setSheet(applied.price_sheet);
      const productId = applied.offers[0]?.product_id || "";
      await refresh(productId);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The price sheet could not be applied.");
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    if (!sheet) return;
    setBusy(true);
    setError("");
    try {
      const rejected = await rejectPriceSheet(sheet.id);
      setSheet(rejected.price_sheet);
      await refresh();
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The price sheet could not be rejected.");
    } finally {
      setBusy(false);
    }
  }

  async function onHistory(productId: string) {
    setHistoryProduct(productId);
    if (!productId) {
      setPoints([]);
      setHistoryName("");
      return;
    }
    try {
      const history = await getPriceHistory(productId);
      setHistoryName(history.product.name);
      setPoints(history.points);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "Price history could not be loaded.");
    }
  }

  return (
    <section className="mt-6 min-w-0 space-y-5" data-testid="supplier-desk">
      <h2 className="text-lg font-medium">Supplier records</h2>
      <label className="lbl" htmlFor="supplier-picker">
        Supplier
        <select
          id="supplier-picker"
          data-testid="supplier-picker"
          className="field"
          value={supplierId}
          onChange={(event) => {
            setSheet(null);
            setPoints([]);
            setError("");
            setSupplierId(event.target.value);
          }}
        >
          {suppliers.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p className="text-sm text-alert" data-testid="supplier-desk-error">
          {error}
        </p>
      ) : null}
      {profile ? (
        <form className="space-y-3" onSubmit={onProfile} data-testid="supplier-profile">
          <h3 className="text-base font-medium">Profile</h3>
          <label className="lbl">
            Rep name
            <input className="field" value={repName} onChange={(event) => setRepName(event.target.value)} />
          </label>
          <label className="lbl">
            Rep email
            <input className="field" type="email" value={repEmail} onChange={(event) => setRepEmail(event.target.value)} />
          </label>
          <label className="lbl">
            Rep phone
            <input className="field" value={repPhone} onChange={(event) => setRepPhone(event.target.value)} />
          </label>
          <fieldset className="space-y-2">
            <legend className="text-sm">Delivery days</legend>
            <div className="flex flex-wrap gap-2">
              {WEEKDAYS.map((day) => (
                <button
                  key={day}
                  type="button"
                  className={days.includes(day) ? "btn btn-primary" : "btn btn-secondary"}
                  aria-pressed={days.includes(day)}
                  onClick={() => toggleDay(day)}
                >
                  {day}
                </button>
              ))}
            </div>
          </fieldset>
          <p data-testid="order-minimum-label">Order minimum {minimumLabel}</p>
          <label className="lbl">
            Order minimum cents
            <input className="field" inputMode="numeric" value={minimum} onChange={(event) => setMinimum(event.target.value)} />
          </label>
          <label className="lbl">
            Currency
            <input className="field" value={currency} maxLength={3} onChange={(event) => setCurrency(event.target.value.toUpperCase())} />
          </label>
          <label className="lbl">
            Payment terms
            <input className="field" value={terms} onChange={(event) => setTerms(event.target.value)} />
          </label>
          <label className="lbl">
            Notes
            <textarea className="field-area" value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Save profile
          </button>
        </form>
      ) : null}

      <form className="space-y-3" onSubmit={onAllocation}>
        <h3 className="text-base font-medium">Allocations</h3>
        <ul className="space-y-2" data-testid="supplier-allocations">
          {allocations.map((row) => (
            <li key={row.id} className="flex min-w-0 items-center justify-between gap-2 rounded-md border border-line px-3 py-2">
              <span className="min-w-0 break-words">
                {row.product_name} · {row.quantity} · {row.period_label}
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  void deleteAllocation(row.id).then(() => refresh());
                }}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        <label className="lbl">
          Product
          <select className="field" value={allocProduct} onChange={(event) => setAllocProduct(event.target.value)}>
            {products.map((row) => (
              <option key={row.product_id} value={row.product_id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
        <label className="lbl">
          Quantity
          <input className="field" inputMode="numeric" value={allocQty} onChange={(event) => setAllocQty(event.target.value)} />
        </label>
        <label className="lbl">
          Period
          <input className="field" value={allocLabel} onChange={(event) => setAllocLabel(event.target.value)} />
        </label>
        <label className="lbl">
          Starts
          <input className="field" type="date" value={allocStart} onChange={(event) => setAllocStart(event.target.value)} />
        </label>
        <label className="lbl">
          Ends
          <input className="field" type="date" value={allocEnd} onChange={(event) => setAllocEnd(event.target.value)} />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={busy || !allocProduct}>
          Add allocation
        </button>
      </form>

      <div className="space-y-2" data-testid="supplier-offers">
        <h3 className="text-base font-medium">Current offers</h3>
        {offers.length === 0 ? <p className="text-sm text-muted">No current offer.</p> : null}
        <ul className="space-y-2">
          {offers.map((offer) => (
            <li key={offer.id} data-testid="supplier-offer" className="rounded-md border border-line px-3 py-2">
              <p className="break-words font-medium">{offer.product_name}</p>
              <p>{offer.price_label}</p>
              <p className="text-sm text-muted">
                {offer.valid_from}
                {offer.valid_to ? ` – ${offer.valid_to}` : " onward"} · {offer.unit || "unit"} · case {offer.case_size} · {offer.source}
              </p>
            </li>
          ))}
        </ul>
      </div>

      <form className="space-y-3" onSubmit={onUpload}>
        <h3 className="text-base font-medium">Price sheet</h3>
        <label className="lbl">
          CSV or PDF
          <input
            data-testid="price-sheet-file"
            className="field-file w-full max-w-full"
            type="file"
            accept=".csv,text/csv,.pdf,application/pdf"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
        </label>
        <button type="submit" className="btn btn-primary" data-testid="price-sheet-upload" disabled={busy || !file}>
          Upload for review
        </button>
      </form>

      {sheet ? (
        <div className="space-y-3" data-testid="price-sheet-review">
          <p>
            Review · {sheet.status} · {sheet.matched} matched · {sheet.unmatched} unmatched
          </p>
          <ul className="space-y-2">
            {sheet.rows.map((row) => (
              <li key={`${sheet.id}-${row.line}`} data-testid="price-sheet-row" className="rounded-md border border-line px-3 py-2">
                <p className="break-words">
                  {row.product_name || row.name || "Untitled"} · {row.price_label}
                </p>
                <p className="text-sm text-muted">
                  {row.status}
                  {row.message ? ` · ${row.message}` : ""}
                </p>
              </li>
            ))}
          </ul>
          {sheet.status === "pending_review" ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-primary" data-testid="price-sheet-apply" disabled={busy} onClick={() => void onApply()}>
                Apply
              </button>
              <button type="button" className="btn btn-secondary" data-testid="price-sheet-reject" disabled={busy} onClick={() => void onReject()}>
                Reject
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-3" data-testid="price-history">
        <h3 className="text-base font-medium">Price history</h3>
        <label className="lbl">
          Product
          <select
            className="field"
            data-testid="price-history-product"
            value={historyProduct}
            onChange={(event) => void onHistory(event.target.value)}
          >
            <option value="">Choose a product</option>
            {products.map((row) => (
              <option key={row.product_id} value={row.product_id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
        {historyName ? <p className="break-words">{historyName}</p> : null}
        <ul className="space-y-2">
          {points.map((point, index) => (
            <li key={`${point.kind}-${point.date}-${point.offer_id || point.invoice_id || index}`} data-testid="price-history-row">
              {point.date} · {point.kind} · {point.price_label} · {point.supplier}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
