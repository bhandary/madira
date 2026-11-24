import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

export const affectedSku = z.object({
  sku: z.string(),
  product_name: z.string(),
  bin_code: z.string(),
  on_hand: z.number(),
});

export const zoneReading = z.object({
  id: z.string().optional(),
  temp_c: z.number(),
  humidity_pct: z.number(),
  recorded_at: z.string().nullable().optional(),
  in_range: z.boolean().optional(),
  source: z.string().optional(),
  notes: z.string().nullable().optional(),
});

export const zoneExcursion = z.object({
  id: z.string(),
  metric: z.string(),
  status: z.string(),
  measured_temp_c: z.number().optional(),
  measured_humidity_pct: z.number().optional(),
  affected_skus: z.array(affectedSku),
  resolution_note: z.string().nullable().optional(),
});

export const zoneCondition = z.object({
  id: z.string(),
  name: z.string(),
  location_id: z.string().nullable().optional(),
  location_name: z.string().nullable().optional(),
  target_temp_min_c: z.number(),
  target_temp_max_c: z.number(),
  target_humidity_min_pct: z.number(),
  target_humidity_max_pct: z.number(),
  notes: z.string().nullable().optional(),
  latest_reading: zoneReading.nullable().optional(),
  status: z.string(),
  excursion: zoneExcursion.nullable().optional(),
});

/** A storage-zone card, or an A2UI path binding resolved before render. */
export const zoneConditionCardProps = z.object({
  zone: z.union([zoneCondition, pathBinding]),
});
