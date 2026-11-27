import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

const jsonObject = z.record(z.unknown());

export const auditEvent = z.object({
  id: z.string(),
  seq: z.number(),
  actor_email: z.string(),
  action: z.string(),
  entity_type: z.string(),
  entity_id: z.string().nullable(),
  before_json: z.union([jsonObject, z.null()]),
  after_json: z.union([jsonObject, z.null()]),
  prev_hash: z.string(),
  event_hash: z.string(),
  created_at: z.string(),
  summary: z.string(),
});

export const auditChain = z.object({
  valid: z.boolean(),
  checked_count: z.number(),
  head_hash: z.string().nullable(),
  broken_event_id: z.string().nullable(),
  reason: z.string().nullable(),
});

/** An audit table, or A2UI path bindings resolved before render. */
export const auditTableProps = z.object({
  events: z.union([z.array(auditEvent), pathBinding]),
  chain: z.union([auditChain, pathBinding]),
});

export type AuditEventRow = z.infer<typeof auditEvent>;
export type AuditChain = z.infer<typeof auditChain>;
