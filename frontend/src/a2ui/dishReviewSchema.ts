import { z } from "zod/v3";

const dish = z.object({
  id: z.string(),
  stable_id: z.string(),
  name: z.string(),
  course: z.string(),
  price: z.number(),
  currency: z.string(),
  main_component: z.string(),
  cooking_method: z.string(),
  sauce: z.string(),
  richness: z.number(),
  acidity: z.number(),
  sweetness: z.number(),
  spice: z.number(),
  umami: z.number(),
  allergens: z.array(z.string()),
  confidence: z.record(z.number()),
  low_confidence: z.array(z.string()),
  needs_repairing: z.boolean(),
});

export const dishReviewValue = z.object({
  menu_id: z.string(),
  version_id: z.string(),
  name: z.string(),
  number: z.number(),
  status: z.string(),
  cuisine: z.string(),
  price_tier: z.string(),
  dishes: z.array(dish),
});

/** A review object, or an A2UI path binding resolved before render. */
export const dishReviewProps = z.object({
  review: z.union([dishReviewValue, z.object({ path: z.string() })]),
});
