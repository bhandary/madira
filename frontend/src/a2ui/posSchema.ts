import { z } from "zod/v3";

export const posStatus = z.object({
  connected: z.boolean(),
  provider: z.string(),
  status: z.string(),
  location_id: z.string(),
  location_name: z.string(),
  key_last4: z.string(),
  masked: z.string(),
  last_synced_at: z.string().nullable(),
  watermark: z.string(),
  demo_mode: z.boolean(),
});

export const posStatusProps = z.object({ status: posStatus }).describe("POS connection for this venue. The access token is not included.");

export const unmappedPosItem = z.object({
  variation_id: z.string(),
  item_id: z.string(),
  name: z.string(),
  quantity: z.string(),
});

export const unmappedPosProps = z
  .object({ items: z.array(unmappedPosItem) })
  .describe("POS items that sold without a SKU mapping.");

export type PosStatusData = z.infer<typeof posStatus>;
export type UnmappedPosItem = z.infer<typeof unmappedPosItem>;
