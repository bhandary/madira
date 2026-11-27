import { z } from "zod/v3";

export const auditorColumn = z.object({
  key: z.string(),
  label: z.string(),
  type: z.enum(["text", "number", "money", "date"]),
});

export const auditorLink = z.object({
  label: z.string(),
  href: z.string(),
});

export const auditorRow = z.object({
  id: z.string(),
  cells: z.record(z.union([z.string(), z.number()])),
  links: z.array(auditorLink),
});

export const auditorTable = z.object({
  title: z.string(),
  columns: z.array(auditorColumn),
  rows: z.array(auditorRow),
  totals: z.record(z.union([z.string(), z.number()])),
  page: z.object({
    limit: z.number(),
    offset: z.number(),
    total: z.number(),
  }),
});

const pathBinding = z.object({ path: z.string() });

export const auditorTableProps = z.object({
  table: z.union([auditorTable, pathBinding]),
});

export type AuditorTableData = z.infer<typeof auditorTable>;
