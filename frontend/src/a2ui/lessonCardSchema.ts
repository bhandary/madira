import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

const cited = z.object({
  id: z.string(),
  slug: z.string().optional(),
  title: z.string(),
});

const bottle = z.object({
  sku_id: z.string(),
  name: z.string(),
});

export const lessonPayload = z.object({
  id: z.string(),
  slug: z.string().optional(),
  title: z.string(),
  body: z.string(),
  position: z.string(),
  role: z.string().optional(),
  category: z.string().optional(),
  status: z.string(),
  source: z.string().optional(),
  can_author: z.boolean(),
  quiz_id: z.string().nullable().optional(),
  standards: z.array(cited).optional(),
  bottles: z.array(bottle).optional(),
  standard_ids: z.array(z.string()).optional(),
  sku_ids: z.array(z.string()).optional(),
});

/** One lesson, or an A2UI path binding resolved before render. */
export const lessonCardProps = z.object({
  lesson: z.union([lessonPayload, pathBinding]),
});

export type LessonPayload = z.infer<typeof lessonPayload>;
