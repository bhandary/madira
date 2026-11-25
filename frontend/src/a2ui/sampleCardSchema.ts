import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

const dish = z.object({
  dish_id: z.string(),
  name: z.string(),
  course: z.string(),
  score: z.number(),
  confidence: z.string(),
});

const listPrice = z.object({
  bottle_price: z.number().nullable(),
  glass_price: z.number().nullable(),
  bottle_label: z.string(),
  glass_label: z.string(),
  margin_pct: z.number().nullable(),
  margin_label: z.string(),
  cost_cents: z.number().nullable(),
  cost_label: z.string(),
  currency: z.string(),
  source: z.string(),
  note: z.string(),
});

const pairsWith = z.object({
  profile: z.string(),
  note: z.string(),
  dishes: z.array(dish),
});

export const sampleCard = z.object({
  id: z.string(),
  session_id: z.string(),
  product_id: z.string().nullable(),
  product_name: z.string(),
  sku_id: z.string().nullable(),
  supplier_id: z.string().nullable(),
  supplier: z.string(),
  offer_id: z.string().nullable(),
  label_document_id: z.string().nullable(),
  matched: z.boolean(),
  score: z.number().nullable(),
  note: z.string(),
  quoted_price_cents: z.number().nullable(),
  currency: z.string().nullable(),
  quoted_label: z.string(),
  decision: z.enum(["undecided", "buy", "list", "pass"]),
  list_price: listPrice,
  pairs_with: pairsWith,
});

export const sampleCardProps = z.object({
  sample: z.union([sampleCard, pathBinding]),
});

export type SampleCardData = z.infer<typeof sampleCard>;
export type SampleProductOption = { id: string; name: string };
