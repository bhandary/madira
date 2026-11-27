import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

const question = z.object({
  id: z.string(),
  prompt: z.string(),
  choices: z.array(z.string()),
  kind: z.string().optional(),
});

const review = z.object({
  id: z.string(),
  prompt: z.string(),
  selected: z.number(),
  ok: z.boolean(),
  explain: z.string(),
});

export const quizPayload = z.object({
  id: z.string(),
  lesson_id: z.string().nullable().optional(),
  title: z.string(),
  status: z.string().optional(),
  source: z.string().optional(),
  questions: z.array(question),
  score: z.number().nullable().optional(),
  score_bp: z.number().nullable().optional(),
  correct: z.number().nullable().optional(),
  total: z.number().nullable().optional(),
  review: z.array(review).optional(),
  next_review_at: z.string().nullable().optional(),
  next_review_on: z.string().nullable().optional(),
  name: z.string().optional(),
});

/** A quiz card, or an A2UI path binding resolved before render. */
export const quizCardProps = z.object({
  quiz: z.union([quizPayload, pathBinding]),
});

export type QuizPayload = z.infer<typeof quizPayload>;
