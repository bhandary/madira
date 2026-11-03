export type A2UIComponent = {
  id: string;
  component: string;
  [key: string]: unknown;
};

export type A2UIOperation = {
  version?: string;
  createSurface?: { surfaceId: string; catalogId?: string };
  updateComponents?: { surfaceId: string; components: A2UIComponent[] };
  updateDataModel?: { surfaceId: string; path?: string; value: unknown };
  deleteSurface?: { surfaceId: string };
};

export type SurfaceState = {
  surfaceId: string;
  catalogId: string;
  components: Record<string, A2UIComponent>;
  data: Record<string, unknown>;
};

function pointerGet(root: unknown, path: string): unknown {
  if (!path || path === "/") return root;
  const parts = path.replace(/^\//, "").split("/").filter(Boolean);
  let cur: unknown = root;
  for (const part of parts) {
    if (cur == null) return undefined;
    if (Array.isArray(cur)) cur = cur[Number(part)];
    else cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function pointerSet(root: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  if (!path || path === "/") {
    return (value && typeof value === "object" && !Array.isArray(value)
      ? { ...root, ...(value as object) }
      : { value }) as Record<string, unknown>;
  }
  const parts = path.replace(/^\//, "").split("/").filter(Boolean);
  const clone: Record<string, unknown> = { ...root };
  let cur: Record<string, unknown> = clone;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i];
    const next = cur[key];
    const obj =
      next && typeof next === "object" && !Array.isArray(next)
        ? { ...(next as Record<string, unknown>) }
        : {};
    cur[key] = obj;
    cur = obj;
  }
  cur[parts[parts.length - 1]] = value;
  return clone;
}

export function resolveBinding(value: unknown, data: unknown): unknown {
  if (value && typeof value === "object" && !Array.isArray(value) && "path" in (value as object)) {
    return pointerGet(data, String((value as { path: string }).path));
  }
  return value;
}

export function applyOperations(operations: A2UIOperation[]): SurfaceState[] {
  const surfaces = new Map<string, SurfaceState>();
  for (const op of operations) {
    if (op.createSurface) {
      surfaces.set(op.createSurface.surfaceId, {
        surfaceId: op.createSurface.surfaceId,
        catalogId: op.createSurface.catalogId || "madira://beverage-catalog",
        components: {},
        data: {},
      });
    }
    if (op.updateComponents) {
      const id = op.updateComponents.surfaceId;
      const existing =
        surfaces.get(id) ||
        ({ surfaceId: id, catalogId: "madira://beverage-catalog", components: {}, data: {} } satisfies SurfaceState);
      for (const component of op.updateComponents.components) {
        existing.components[component.id] = component;
      }
      surfaces.set(id, existing);
    }
    if (op.updateDataModel) {
      const id = op.updateDataModel.surfaceId;
      const existing =
        surfaces.get(id) ||
        ({ surfaceId: id, catalogId: "madira://beverage-catalog", components: {}, data: {} } satisfies SurfaceState);
      existing.data = pointerSet(existing.data, op.updateDataModel.path || "/", op.updateDataModel.value);
      surfaces.set(id, existing);
    }
    if (op.deleteSurface) {
      surfaces.delete(op.deleteSurface.surfaceId);
    }
  }
  return [...surfaces.values()];
}
