import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

export const pricePoint = z.object({
  date: z.string(),
  kind: z.string(),
  price_cents: z.number(),
  price_label: z.string(),
  currency: z.string(),
  supplier_id: z.string(),
  supplier: z.string(),
  source: z.string(),
  offer_id: z.string().nullable(),
  invoice_id: z.string().nullable(),
});

export const priceHistoryProduct = z.object({
  id: z.string(),
  name: z.string(),
  producer: z.string(),
});

export type PricePoint = z.infer<typeof pricePoint>;
export type PriceHistoryProduct = z.infer<typeof priceHistoryProduct>;

export const priceHistoryProps = z.object({
  product: z.union([priceHistoryProduct, pathBinding]),
  points: z.union([z.array(pricePoint), pathBinding]),
});
