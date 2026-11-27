import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

const turn = z.object({
  role: z.enum(["guest", "staff"]),
  text: z.string(),
  product_ids: z.array(z.string()).optional(),
});

const criterion = z.object({
  pass: z.boolean(),
  evidence: z.string(),
});

export const roleplaySession = z.object({
  id: z.string(),
  persona: z.string(),
  dish_id: z.string().nullable(),
  dish_name: z.string(),
  status: z.enum(["open", "scored"]),
  transcript: z.array(turn),
  rubric: z
    .object({
      listened: criterion,
      offered_two_options: criterion,
      described_structure: criterion,
      handled_price: criterion,
    })
    .nullable(),
  score: z.number().int().min(0).max(4).nullable(),
  started_at: z.string().nullable(),
  scored_at: z.string().nullable(),
});

/** A roleplay panel, or an A2UI path binding resolved before render. */
export const roleplayPanelProps = z.object({
  session: z.union([roleplaySession, pathBinding]),
});

export type RoleplaySession = z.infer<typeof roleplaySession>;
