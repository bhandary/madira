import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

export const approvalPurchaseOrder = z.object({
  id: z.string(),
  po_number: z.string().optional(),
  supplier: z.string().optional(),
  status: z.string().optional(),
  subtotal_cents: z.number().optional(),
  order_minimum_cents: z.number().optional(),
  minimum_met: z.boolean().optional(),
  shortfall_cents: z.number().optional(),
  expected_delivery_date: z.string().optional(),
  currency: z.string().optional(),
});

export const approvalRecord = z.object({
  id: z.string().optional(),
  decision: z.string().optional(),
  required_role: z.string().optional(),
  comment: z.string().nullable().optional(),
  decided_at: z.string().nullable().optional(),
});

/** An owner decision card, or A2UI path bindings resolved before render. */
export const approvalCardProps = z.object({
  purchaseOrder: z.union([approvalPurchaseOrder, pathBinding]),
  approval: z.union([approvalRecord, pathBinding]),
});
