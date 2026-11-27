import { z } from "zod/v3";

const pathBinding = z.object({ path: z.string() });

export const supplierOffer = z.object({
  id: z.string(),
  supplier_id: z.string(),
  supplier: z.string(),
  product_id: z.string(),
  product_name: z.string(),
  sku_id: z.string().nullable(),
  sku: z.string(),
  unit: z.string(),
  case_size: z.number(),
  price_cents: z.number(),
  price_label: z.string(),
  currency: z.string(),
  valid_from: z.string(),
  valid_to: z.string().nullable(),
  source: z.string(),
  source_document_id: z.string().nullable(),
  price_sheet_id: z.string().nullable(),
});

export type SupplierOfferCard = z.infer<typeof supplierOffer>;

export const supplierOffersProps = z.object({
  offers: z.union([z.array(supplierOffer), pathBinding]),
  supplier: z.union([z.string(), pathBinding]).optional(),
});
