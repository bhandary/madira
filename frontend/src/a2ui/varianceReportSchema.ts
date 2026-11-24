import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

export const varianceLine = z.object({
  sku: z.string(),
  name: z.string(),
  counted_quantity: z.number().nullable(),
  expected_quantity: z.number(),
  variance: z.number().nullable(),
  variance_value_cents: z.number().nullable(),
  unit_cost_cents: z.number(),
});

export const conflictReading = z.object({
  device_id: z.string(),
  counted_quantity: z.number(),
  counted_at: z.string().nullable().optional(),
});

export const countConflict = z.object({
  sku: z.string(),
  readings: z.array(conflictReading),
  resolved: z.boolean(),
  resolved_quantity: z.number().nullable(),
});

export const varianceReport = z.object({
  session: z.object({
    id: z.string(),
    status: z.string(),
    location_name: z.string().optional(),
  }),
  lines: z.array(varianceLine),
  conflicts: z.array(countConflict),
});

/** A variance report, or an A2UI path binding resolved before render. */
export const varianceReportProps = z.object({
  report: z.union([varianceReport, pathBinding]),
});
