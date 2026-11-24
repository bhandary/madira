import { z } from "zod/v3";

const pathBinding = z.union([z.string(), z.object({ path: z.string() })]);

const briefingItem = z.object({
  title: z.string(),
  detail: z.string(),
});

const briefingCard = z.object({
  kind: z.string(),
  title: z.string(),
  body: z.string(),
  items: z.array(briefingItem),
});

export const briefingPayload = z.object({
  id: z.string(),
  service_date: z.string(),
  status: z.string(),
  intro: z.string(),
  cards: z.array(briefingCard),
  due_review_count: z.number().int().nonnegative(),
  acknowledged: z.boolean(),
  seconds_to_ack: z.number().int().nonnegative().nullable(),
});

export const briefingCardsProps = z
  .object({
    title: pathBinding.optional(),
    briefing: z.union([briefingPayload, z.object({ path: z.string() })]),
  })
  .strict();

export type BriefingPayload = z.infer<typeof briefingPayload>;
