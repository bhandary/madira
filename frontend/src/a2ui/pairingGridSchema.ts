import { z } from "zod/v3";

const slot = z.object({
  id: z.string(),
  slot: z.string(),
  status: z.string(),
  sku_id: z.string().nullable(),
  category: z.string(),
  name: z.string(),
  producer: z.string(),
  region: z.string(),
  style: z.string(),
  rationale: z.string(),
  server_script: z.string(),
  confidence: z.string(),
  price_tier: z.string(),
  glass_price: z.number(),
  bottle_price: z.number(),
  currency: z.string(),
  gap: z.string(),
});

const option = z.object({
  sku_id: z.string(),
  name: z.string(),
  producer: z.string(),
  category: z.string(),
  style: z.string(),
});

export const pairingDish = z.object({
  id: z.string(),
  stable_id: z.string(),
  name: z.string(),
  dish: z.string(),
  course: z.string(),
  flavor_profile: z.string(),
  price: z.number(),
  currency: z.string(),
  needs_repairing: z.boolean(),
  options: z.array(option),
  pairings: z.array(slot),
});

const pathBinding = z.object({ path: z.string() });

/** A pairing grid, or A2UI path bindings resolved before render. */
export const pairingGridProps = z.object({
  menu_id: z.union([z.string(), pathBinding]),
  dishes: z.union([z.array(pairingDish), pathBinding]),
});

export type PairingSlot = z.infer<typeof slot>;
export type PairingOption = z.infer<typeof option>;
export type PairingDish = z.infer<typeof pairingDish>;
