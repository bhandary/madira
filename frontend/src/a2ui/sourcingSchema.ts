import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

const dish = z.object({
  dish_id: z.string(),
  name: z.string(),
});

const wantItem = z.object({
  id: z.string(),
  category: z.string(),
  style: z.string(),
  price_band: z.string(),
  quantity_hint: z.number(),
  dishes: z.array(dish),
  sample_id: z.string().nullable(),
  offer_id: z.string().nullable(),
  rationale: z.string(),
  position: z.number(),
});

export const sourcingBrief = z.object({
  id: z.string(),
  list_id: z.string().nullable(),
  title: z.string(),
  status: z.string(),
  items: z.array(wantItem),
});

export const sourcingBriefProps = z.object({
  brief: z.union([sourcingBrief, pathBinding]),
});

export const repFollowup = z.object({
  id: z.string(),
  session_id: z.string(),
  supplier_id: z.string().nullable(),
  supplier: z.string(),
  to_email: z.string(),
  subject: z.string(),
  body: z.string(),
  purchase_order_id: z.string().nullable(),
  purchase_order_number: z.string(),
  mailto: z.string(),
  sent: z.boolean(),
});

export const repFollowupProps = z.object({
  followup: z.union([repFollowup, pathBinding]),
});

const historyRow = z.object({
  supplier_id: z.string(),
  supplier: z.string(),
  product_id: z.string(),
  product: z.string(),
  tasted: z.number(),
  buy: z.number(),
  list: z.number(),
  pass: z.number(),
  undecided: z.number(),
  bought_bottles: z.number(),
  invoiced_bottles: z.number(),
  last_cost_cents: z.number().nullable(),
  last_cost_label: z.string(),
});

export const tastingHistory = z.object({
  rows: z.array(historyRow),
});

export const tastingHistoryProps = z.object({
  history: z.union([tastingHistory, pathBinding]),
});

export type SourcingBriefData = z.infer<typeof sourcingBrief>;
export type RepFollowupData = z.infer<typeof repFollowup>;
export type TastingHistoryData = z.infer<typeof tastingHistory>;
