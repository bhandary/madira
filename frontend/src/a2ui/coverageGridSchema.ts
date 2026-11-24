import { z } from "zod/v3";

export const coverageCell = z.object({
  category: z.string(),
  style: z.string(),
  band: z.string(),
  status: z.string(),
  product_id: z.string().nullable(),
  sku_id: z.string().nullable(),
  name: z.string(),
  dish_id: z.string().nullable(),
  dish_name: z.string(),
});

const pathBinding = z.object({ path: z.string() });

/** A coverage matrix, or A2UI path bindings resolved before render. */
export const coverageGridProps = z.object({
  cells: z.union([z.array(coverageCell), pathBinding]),
});

export type CoverageCell = z.infer<typeof coverageCell>;
