"use client";

import { createCatalog } from "@copilotkit/a2ui-renderer";
import { z } from "zod/v3";
import { renderMadiraComponent } from "@/components/A2UISurface";
import { MADIRA_CATALOG_ID, catalogDefinitions } from "./definitions";

/**
 * Wire values are either literals or `{ path }` bindings. The A2UI binder
 * treats a union that contains a `{ path }` object as a dynamic value and
 * resolves it before the renderer runs. Prop names come from catalogDefinitions.
 */
const dynamicValue = z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.array(z.any()),
  z.record(z.any()),
  z.object({ path: z.string() }),
]);

function schemaFor(props: object) {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const key of Object.keys(props)) shape[key] = dynamicValue;
  return z.object(shape);
}

const definitions = Object.fromEntries(
  Object.entries(catalogDefinitions).map(([name, def]) => [
    name,
    {
      description: def.description,
      props: schemaFor(def.props).describe(def.description),
    },
  ]),
);

const renderers = Object.fromEntries(
  Object.keys(catalogDefinitions).map((name) => [
    name,
    ({ props }: { props: Record<string, unknown> }) => renderMadiraComponent(name, props),
  ]),
);

// createCatalog's published types are bound to the Zod 3 copy inside
// @copilotkit/a2ui-renderer. These schemas are Zod 3 (`zod/v3`) with the
// `_def.typeName` shape the A2UI binder reads; the classes are not the same type.
export const beverageCatalog = createCatalog(
  definitions as never,
  renderers as never,
  { catalogId: MADIRA_CATALOG_ID, includeBasicCatalog: true },
);

/** Catalog id used by A2UI createSurface operations. */
export const catalogId = MADIRA_CATALOG_ID;
