import { z } from "zod/v3";

const pathBinding = z.union([z.string(), z.object({ path: z.string() })]);

export const lookupHit = z.object({
  name: z.string(),
  producer: z.string(),
  grape: z.string(),
  region: z.string(),
  pairing: z.string(),
  server_script: z.string(),
  flavor_profile: z.string(),
  glassware: z.string(),
  serving_temperature: z.string(),
  pour_size: z.string(),
  stock: z.union([z.string(), z.number()]),
  price_cents: z.number().int().nonnegative(),
  currency: z.string(),
});

export const lookupPayload = z.object({
  query: z.string(),
  results: z.array(lookupHit),
});

export const floorLookupProps = z
  .object({
    title: pathBinding.optional(),
    lookup: z.union([lookupPayload, z.object({ path: z.string() })]),
  })
  .strict();

export type LookupPayload = z.infer<typeof lookupPayload>;
