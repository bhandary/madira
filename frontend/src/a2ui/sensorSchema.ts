import { z } from "zod/v3";

export const sensorStatusItem = z.object({
  id: z.string(),
  name: z.string(),
  zone_name: z.string(),
  location_name: z.string(),
  metric: z.string(),
  external_id: z.string(),
  masked: z.string(),
  last_value: z.string(),
  last_at: z.string().nullable(),
  stale: z.boolean(),
  stale_after_hours: z.number(),
});

export const sensorStatusProps = z
  .object({ sensors: z.array(sensorStatusItem) })
  .describe("Sensor last reading and stale state. The signing secret is not included.");

export const reminderItem = z.object({
  source_type: z.string(),
  source_id: z.string(),
  title: z.string(),
  detail: z.string(),
  due_on: z.string(),
  days_left: z.number(),
  label: z.string(),
  channel: z.string(),
});

export const reminderListProps = z
  .object({ reminders: z.array(reminderItem) })
  .describe("Open in-app reminders. Nothing is sent.");

export type SensorStatusItem = z.infer<typeof sensorStatusItem>;
export type ReminderItem = z.infer<typeof reminderItem>;
