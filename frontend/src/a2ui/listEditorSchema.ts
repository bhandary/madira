import { z } from "zod/v3";

const item = z.object({
  id: z.string(),
  sku_id: z.string(),
  product_id: z.string().nullable(),
  section: z.string(),
  position: z.number(),
  category: z.string(),
  name: z.string(),
  producer: z.string(),
  style: z.string(),
  band: z.string(),
  pour_price: z.number(),
  bottle_price: z.number(),
  currency: z.string(),
  margin_pct: z.number().optional(),
  beverage_cost_pct: z.number().optional(),
});

const section = z.object({
  id: z.string(),
  name: z.string(),
  position: z.number(),
  budget_share_pct: z.number().nullable(),
  item_count: z.number(),
  margin_pct: z.number().optional(),
  beverage_cost_pct: z.number().optional(),
});

export const candidate = z.object({
  sku_id: z.string(),
  product_id: z.string(),
  name: z.string(),
  category: z.string(),
  style: z.string(),
  band: z.string(),
});

const pathBinding = z.object({ path: z.string() });

/** A list editor, or A2UI path bindings resolved before render. */
export const listEditorProps = z.object({
  listId: z.union([z.string(), pathBinding]),
  currency: z.union([z.string(), pathBinding]),
  sections: z.union([z.array(section), pathBinding]),
  items: z.union([z.array(item), pathBinding]),
  candidates: z.union([z.array(candidate), pathBinding]),
});

export type EditorItem = z.infer<typeof item>;
export type EditorSection = z.infer<typeof section>;
export type EditorCandidate = z.infer<typeof candidate>;
