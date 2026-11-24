import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

export const countSession = z.object({
  id: z.string(),
  status: z.string(),
  location_name: z.string().optional(),
  location_id: z.string().optional(),
  notes: z.string().optional(),
});

export const countLine = z.object({
  id: z.string(),
  sku: z.string(),
  name: z.string(),
  counted_quantity: z.number(),
  expected_quantity: z.number().nullable().optional(),
  device_id: z.string(),
  bin_code: z.string().optional(),
  counted_at: z.string().nullable().optional(),
});

/** A count sheet, or A2UI path bindings resolved before render. */
export const countSheetProps = z.object({
  session: z.union([countSession, pathBinding]),
  lines: z.union([z.array(countLine), pathBinding]),
});
