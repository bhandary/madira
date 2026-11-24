import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

export const receivingPurchaseOrder = z.object({
  id: z.string(),
  po_number: z.string().optional(),
  supplier: z.string().optional(),
  status: z.string().optional(),
});

export const receivingReceipt = z.object({
  id: z.string().optional(),
  status: z.string().optional(),
  invoice_id: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  discrepancy_summary: z.record(z.any()).optional(),
});

export const receivingLine = z.object({
  id: z.string().optional(),
  po_line_id: z.string().nullable().optional(),
  sku: z.string(),
  product_name: z.string().optional(),
  ordered_qty: z.number().optional(),
  invoiced_qty: z.number().nullable().optional(),
  counted_qty: z.number().optional(),
  ordered_unit_cost_cents: z.number().optional(),
  invoiced_unit_cost_cents: z.number().nullable().optional(),
  ordered_vintage: z.string().nullable().optional(),
  received_vintage: z.string().nullable().optional(),
  bin_id: z.string().nullable().optional(),
  flags: z.array(z.string()).optional(),
  cost_delta_cents: z.number().optional(),
});

/** A counted delivery, or A2UI path bindings resolved before render. */
export const receivingChecklistProps = z.object({
  purchaseOrder: z.union([receivingPurchaseOrder, pathBinding]),
  receipt: z.union([receivingReceipt, pathBinding]),
  lines: z.union([z.array(receivingLine), pathBinding]),
});
