"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApprovalCard } from "@/components/ApprovalCard";
import {
  ApiError,
  addSupplierContact,
  cancelPurchaseOrder,
  closePurchaseOrder,
  createLifecycleOrder,
  createProcurementSupplier,
  draftLifecycleOrders,
  listLifecycleOrders,
  listProcurementSuppliers,
  sendPurchaseOrder,
  type PurchaseOrderRow,
  type SupplierRow,
} from "@/lib/api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function money(cents: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format((cents || 0) / 100);
}

function nextDelivery(days: string[], lead: number) {
  const start = new Date();
  start.setUTCHours(12, 0, 0, 0);
  start.setUTCDate(start.getUTCDate() + Math.max(0, lead || 0));
  if (!days.length) return start.toISOString().slice(0, 10);
  for (let offset = 0; offset < 21; offset += 1) {
    const candidate = new Date(start);
    candidate.setUTCDate(start.getUTCDate() + offset);
    const label = WEEKDAYS[(candidate.getUTCDay() + 6) % 7];
    if (days.includes(label)) return candidate.toISOString().slice(0, 10);
  }
  return start.toISOString().slice(0, 10);
}

function statusClass(status: string) {
  if (status === "approved" || status === "received" || status === "closed") return "badge badge-ok";
  if (status === "canceled") return "badge badge-alert";
  if (status === "sent" || status === "part_received") return "badge badge-wine";
  return "badge badge-draft";
}

export default function PurchasingPage() {
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [orders, setOrders] = useState<PurchaseOrderRow[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const [supplierName, setSupplierName] = useState("");
  const [supplierCase, setSupplierCase] = useState("12");
  const [supplierMinimum, setSupplierMinimum] = useState("0");
  const [supplierDays, setSupplierDays] = useState("Tue, Thu");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");

  const [draftSupplierId, setDraftSupplierId] = useState("");
  const [draftSku, setDraftSku] = useState("W-MUS-01");
  const [draftName, setDraftName] = useState("Muscadet Domaine de l'Ecu");
  const [draftBottles, setDraftBottles] = useState("6");
  const [draftCost, setDraftCost] = useState("1800");

  async function refresh(nextId?: string) {
    const [directory, ledger] = await Promise.all([listProcurementSuppliers(), listLifecycleOrders()]);
    setSuppliers(directory.suppliers);
    setOrders(ledger.orders);
    setDraftSupplierId((current) => current || directory.suppliers[0]?.id || "");
    if (nextId) setSelectedId(nextId);
    setLoaded(true);
    setError("");
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([listProcurementSuppliers(), listLifecycleOrders()])
      .then(([directory, ledger]) => {
        if (cancelled) return;
        setSuppliers(directory.suppliers);
        setOrders(ledger.orders);
        setDraftSupplierId(directory.suppliers[0]?.id || "");
        setLoaded(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoaded(true);
        setError(err instanceof Error ? err.message : "Purchasing could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedSupplier = suppliers.find((row) => row.id === draftSupplierId) || null;
  const preview = useMemo(() => {
    const caseSize = selectedSupplier?.default_case_size || 12;
    const bottles = Math.max(0, Number(draftBottles) || 0);
    const cases = bottles === 0 ? 0 : Math.ceil(bottles / caseSize);
    const quantity = cases * caseSize;
    const subtotal = quantity * (Number(draftCost) || 0);
    const minimum = selectedSupplier?.order_minimum_cents || 0;
    return {
      caseSize,
      cases,
      quantity,
      subtotal,
      minimum,
      met: subtotal >= minimum,
      shortfall: Math.max(0, minimum - subtotal),
      delivery: nextDelivery(selectedSupplier?.delivery_days || [], selectedSupplier?.lead_time_days || 0),
    };
  }, [selectedSupplier, draftBottles, draftCost]);

  const selected = orders.find((row) => row.id === selectedId) || null;

  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  function addSupplier(event: FormEvent) {
    event.preventDefault();
    const days = supplierDays
      .split(",")
      .map((day) => day.trim())
      .filter(Boolean);
    void run(async () => {
      const created = await createProcurementSupplier({
        name: supplierName,
        default_case_size: Number(supplierCase) || 12,
        order_minimum_cents: Number(supplierMinimum) || 0,
        delivery_days: days,
        lead_time_days: 7,
      });
      setSupplierName("");
      setDraftSupplierId(created.supplier.id);
      await refresh();
    });
  }

  function addContact(event: FormEvent) {
    event.preventDefault();
    if (!draftSupplierId) return;
    void run(async () => {
      await addSupplierContact(draftSupplierId, {
        name: contactName,
        email: contactEmail,
        is_primary: true,
      });
      setContactName("");
      setContactEmail("");
      await refresh();
    });
  }

  function draftManual(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const created = await createLifecycleOrder({
        supplier_id: draftSupplierId,
        lines: [
          {
            sku: draftSku,
            product_name: draftName,
            bottles: Number(draftBottles) || 0,
            unit_cost_cents: Number(draftCost) || 0,
          },
        ],
      });
      await refresh(created.id);
    });
  }

  return (
    <div className="min-w-0" data-testid="purchasing-page">
      <h1 className="h-page">Purchasing</h1>
      <p className="lead">
        Draft a purchase order by the case. Every order waits for the Owner. Sending archives the PDF in the document vault and does not email the supplier.
      </p>
      {error ? (
        <p className="banner-error mt-4" role="alert" data-testid="purchasing-error">
          {error}
        </p>
      ) : null}

      <section className="mt-6" aria-labelledby="suppliers-heading">
        <h2 id="suppliers-heading" className="text-lg font-medium">
          Suppliers
        </h2>
        <div className="mt-3 grid gap-3">
          {suppliers.map((supplier) => (
            <article
              key={supplier.id}
              className="panel min-w-0 p-3"
              data-testid="supplier-card"
              data-name={supplier.name}
            >
              <h3 className="break-words text-sm font-medium">{supplier.name}</h3>
              <p className="mt-1 text-sm text-muted">
                <span data-testid="supplier-case-size">Case {supplier.default_case_size}</span>
                {" · "}
                <span data-testid="supplier-minimum">{money(supplier.order_minimum_cents)} minimum</span>
                {" · "}
                <span data-testid="supplier-delivery-days">{supplier.delivery_days.join(", ") || "any day"}</span>
              </p>
              <ul className="mt-2 space-y-1">
                {supplier.contacts.map((contact) => (
                  <li key={contact.id} className="break-words text-sm" data-testid="supplier-contact">
                    {contact.name}
                    {contact.role ? ` · ${contact.role}` : ""} · {contact.email}
                  </li>
                ))}
              </ul>
            </article>
          ))}
          {loaded && suppliers.length === 0 ? <p className="text-sm text-muted">No suppliers yet.</p> : null}
        </div>
        <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={addSupplier}>
          <label className="lbl" htmlFor="supplier-name">
            Supplier
            <input
              id="supplier-name"
              data-testid="add-supplier-name"
              className="field w-full"
              value={supplierName}
              onChange={(event) => setSupplierName(event.target.value)}
              required
            />
          </label>
          <label className="lbl" htmlFor="supplier-case">
            Case size
            <input
              id="supplier-case"
              data-testid="add-supplier-case"
              className="field w-full"
              inputMode="numeric"
              value={supplierCase}
              onChange={(event) => setSupplierCase(event.target.value)}
            />
          </label>
          <label className="lbl" htmlFor="supplier-minimum">
            Minimum (cents)
            <input
              id="supplier-minimum"
              className="field w-full"
              inputMode="numeric"
              value={supplierMinimum}
              onChange={(event) => setSupplierMinimum(event.target.value)}
            />
          </label>
          <label className="lbl" htmlFor="supplier-days">
            Delivery days
            <input
              id="supplier-days"
              className="field w-full"
              value={supplierDays}
              onChange={(event) => setSupplierDays(event.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-secondary sm:col-span-2" data-testid="add-supplier" disabled={busy}>
            Add supplier
          </button>
        </form>
        <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={addContact}>
          <label className="lbl" htmlFor="contact-name">
            Contact
            <input
              id="contact-name"
              data-testid="add-contact-name"
              className="field w-full"
              value={contactName}
              onChange={(event) => setContactName(event.target.value)}
              required
            />
          </label>
          <label className="lbl" htmlFor="contact-email">
            Email
            <input
              id="contact-email"
              data-testid="add-contact-email"
              className="field w-full"
              type="email"
              value={contactEmail}
              onChange={(event) => setContactEmail(event.target.value)}
              required
            />
          </label>
          <button type="submit" className="btn btn-secondary sm:col-span-2" data-testid="add-contact" disabled={busy || !draftSupplierId}>
            Add contact
          </button>
        </form>
      </section>

      <section className="mt-8" aria-labelledby="draft-heading">
        <h2 id="draft-heading" className="text-lg font-medium">
          Draft
        </h2>
        <button
          type="button"
          className="btn btn-primary mt-3 max-w-full whitespace-normal"
          data-testid="draft-from-reorder"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const drafted = await draftLifecycleOrders();
              await refresh(drafted.orders[0]?.id);
            })
          }
        >
          Draft POs from low stock
        </button>
        <form className="mt-4 grid gap-3" onSubmit={draftManual}>
          <label className="lbl" htmlFor="draft-supplier">
            Supplier
            <select
              id="draft-supplier"
              data-testid="draft-supplier"
              className="field w-full"
              value={draftSupplierId}
              onChange={(event) => setDraftSupplierId(event.target.value)}
            >
              {suppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
          </label>
          <label className="lbl" htmlFor="draft-sku">
            SKU
            <input
              id="draft-sku"
              data-testid="draft-sku"
              className="field w-full font-mono"
              value={draftSku}
              onChange={(event) => setDraftSku(event.target.value)}
              required
            />
          </label>
          <label className="lbl" htmlFor="draft-name">
            Product
            <input
              id="draft-name"
              data-testid="draft-name"
              className="field w-full"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              required
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="lbl" htmlFor="draft-bottles">
              Bottles needed
              <input
                id="draft-bottles"
                data-testid="draft-bottles"
                className="field w-full"
                inputMode="numeric"
                value={draftBottles}
                onChange={(event) => setDraftBottles(event.target.value)}
              />
            </label>
            <label className="lbl" htmlFor="draft-cost">
              Unit cost (cents)
              <input
                id="draft-cost"
                data-testid="draft-cost"
                className="field w-full"
                inputMode="numeric"
                value={draftCost}
                onChange={(event) => setDraftCost(event.target.value)}
              />
            </label>
          </div>
          <p className="text-sm" data-testid="draft-cases">
            {preview.cases === 1 ? "1 case" : `${preview.cases} cases`} of {preview.caseSize}
          </p>
          <p className="text-sm" data-testid="draft-quantity">
            {preview.quantity} bottles · {money(preview.subtotal)}
          </p>
          <p className="text-sm" data-testid="draft-minimum">
            {preview.met ? "Minimum met" : `Minimum not met · short ${money(preview.shortfall)}`}
          </p>
          <p className="text-sm" data-testid="draft-delivery">
            Next delivery {preview.delivery}
          </p>
          <button type="submit" className="btn btn-primary max-w-full" data-testid="draft-submit" disabled={busy || !draftSupplierId}>
            Draft PO
          </button>
        </form>
      </section>

      <section className="mt-8" aria-labelledby="orders-heading">
        <h2 id="orders-heading" className="text-lg font-medium">
          Purchase orders
        </h2>
        <div className="mt-3 grid gap-3">
          {orders.map((order) => (
            <button
              key={order.id}
              type="button"
              className="panel min-w-0 p-3 text-left"
              data-testid="po-card"
              data-po={order.po_number || ""}
              data-status={order.status}
              onClick={() => setSelectedId(order.id)}
            >
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium">{order.po_number}</span>
                <span className={statusClass(order.status)} data-testid="po-status">
                  {order.status}
                </span>
              </span>
              <span className="mt-1 block break-words text-sm text-muted">
                {order.supplier} · {money(order.subtotal_cents)}
              </span>
            </button>
          ))}
          {loaded && orders.length === 0 ? <p className="text-sm text-muted">No purchase orders yet.</p> : null}
        </div>
        {selected ? (
          <div className="mt-4 min-w-0 space-y-3" data-testid="po-detail">
            <p>
              <span className={statusClass(selected.status)} data-testid="po-status">
                {selected.status}
              </span>
            </p>
            <ApprovalCard
              purchaseOrder={{
                id: selected.id,
                po_number: selected.po_number || "",
                supplier: selected.supplier,
                status: selected.status,
                subtotal_cents: selected.subtotal_cents,
                order_minimum_cents: selected.order_minimum_cents,
                minimum_met: selected.minimum_met,
                shortfall_cents: selected.shortfall_cents,
                expected_delivery_date: selected.expected_delivery_date || "",
              }}
              approval={selected.approval}
              onDecided={() => void refresh(selected.id)}
            />
            <ul className="panel divide-y divide-line" data-testid="po-lines">
              {selected.lines.map((line) => (
                <li key={line.id} className="px-3 py-2 text-sm">
                  <span className="font-mono">{line.sku}</span> {line.product_name || line.name}
                  <span className="mt-1 block text-muted">
                    {line.cases_ordered} cases · {line.quantity_ordered} bottles · {money(line.line_total_cents)}
                  </span>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              {selected.status === "approved" ? (
                <button
                  type="button"
                  className="btn btn-primary max-w-full whitespace-normal"
                  data-testid="po-send"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await sendPurchaseOrder(selected.id);
                      await refresh(selected.id);
                    })
                  }
                >
                  Archive PDF & Mark Sent
                </button>
              ) : null}
              {selected.pdf_document_id ? (
                <a
                  className="btn btn-secondary"
                  data-testid="po-pdf"
                  href={`/madira-api/procurement/orders/${selected.id}/pdf`}
                >
                  Download PO PDF
                </a>
              ) : null}
              {selected.status === "draft" || selected.status === "approved" ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  data-testid="po-cancel"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await cancelPurchaseOrder(selected.id);
                      await refresh(selected.id);
                    })
                  }
                >
                  Cancel
                </button>
              ) : null}
              {selected.status === "received" ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  data-testid="po-close"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await closePurchaseOrder(selected.id);
                      await refresh(selected.id);
                    })
                  }
                >
                  Close
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
