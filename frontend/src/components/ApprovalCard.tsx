"use client";

import { useState } from "react";
import { ApiError, decidePurchaseOrder } from "@/lib/api";

export type ApprovalPurchaseOrder = {
  id: string;
  po_number?: string;
  supplier?: string;
  status?: string;
  subtotal_cents?: number;
  order_minimum_cents?: number;
  minimum_met?: boolean;
  shortfall_cents?: number;
  expected_delivery_date?: string;
  currency?: string;
};

export type ApprovalRecord = {
  id?: string;
  decision?: string;
  required_role?: string;
  comment?: string | null;
  decided_at?: string | null;
};

function money(cents: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format((cents || 0) / 100);
}

export function ApprovalCard({
  purchaseOrder,
  approval,
  onDecided,
}: {
  purchaseOrder: ApprovalPurchaseOrder;
  approval?: ApprovalRecord | null;
  onDecided?: () => void;
}) {
  const decision = approval?.decision || "pending";
  const pending = decision === "pending" && (purchaseOrder.status || "draft") === "draft";
  const [comment, setComment] = useState(approval?.comment || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const minimum = purchaseOrder.order_minimum_cents || 0;
  const subtotal = purchaseOrder.subtotal_cents || 0;
  const met = purchaseOrder.minimum_met !== false && subtotal >= minimum;

  async function decide(next: "approve" | "reject") {
    setBusy(true);
    setError("");
    try {
      await decidePurchaseOrder(purchaseOrder.id, next, comment);
      onDecided?.();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "The decision could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="panel min-w-0 p-3" data-testid="approval-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium">{purchaseOrder.po_number || "Purchase order"}</h3>
        <span className="text-xs uppercase tracking-wide text-muted">{approval?.required_role || "owner"} approval</span>
      </div>
      <p className="mt-1 break-words text-sm text-muted">{purchaseOrder.supplier}</p>
      <p className="mt-2 text-sm">
        Subtotal {money(subtotal)}
        {purchaseOrder.expected_delivery_date ? ` · delivers ${purchaseOrder.expected_delivery_date}` : ""}
      </p>
      <p className="mt-1 text-sm" data-testid="approval-minimum">
        {met ? "Order minimum met" : `Short ${money(purchaseOrder.shortfall_cents || Math.max(0, minimum - subtotal))}`}
      </p>
      {decision !== "pending" ? (
        <p className="mt-2 text-sm" data-testid="approval-decision">
          {decision}
          {approval?.comment ? ` · ${approval.comment}` : ""}
        </p>
      ) : null}
      {pending ? (
        <div className="mt-3 space-y-2">
          <label className="lbl" htmlFor={`po-comment-${purchaseOrder.id}`}>
            Comment
            <textarea
              id={`po-comment-${purchaseOrder.id}`}
              data-testid="po-comment"
              className="field min-h-16 w-full"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-primary"
              data-testid="po-approve"
              disabled={busy}
              onClick={() => void decide("approve")}
            >
              Approve
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              data-testid="po-reject"
              disabled={busy}
              onClick={() => void decide("reject")}
            >
              Reject
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p className="banner-error mt-3" role="alert" data-testid="approval-error">
          {error}
        </p>
      ) : null}
    </article>
  );
}
