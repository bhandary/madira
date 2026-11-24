import type { AuditChain, AuditEventRow } from "@/a2ui/auditTableSchema";

export const API = "/madira-api";

export async function getStatus() {
  const res = await fetch(`${API}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("status failed");
  return res.json();
}

export async function uploadMenu(payload: { text?: string; file?: File }) {
  const body = new FormData();
  if (payload.text) body.set("text", payload.text);
  if (payload.file) body.set("file", payload.file);
  const res = await fetch(`${API}/menus/upload`, { method: "POST", body });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export type MenuDish = {
  id: string;
  stable_id: string;
  name: string;
  course: string;
  price: number;
  currency: string;
  main_component: string;
  cooking_method: string;
  sauce: string;
  richness: number;
  acidity: number;
  sweetness: number;
  spice: number;
  umami: number;
  allergens: string[];
  confidence: Record<string, number>;
  low_confidence: string[];
  needs_repairing: boolean;
};

export type MenuReview = {
  menu_id: string;
  version_id: string;
  name: string;
  number: number;
  status: string;
  cuisine: string;
  price_tier: string;
  dishes: MenuDish[];
};

export type MenuIngestResult = {
  menu_id: string;
  version_id: string;
  name: string;
  status: string;
  review: MenuReview;
};

export async function ingestMenu(input: {
  file?: File | null;
  url?: string;
  text?: string;
  menuId?: string;
}): Promise<MenuIngestResult> {
  const body = new FormData();
  if (input.file) body.set("file", input.file);
  if (input.url) body.set("url", input.url);
  if (input.text) body.set("text", input.text);
  if (input.menuId) body.set("menu_id", input.menuId);
  const res = await fetch(`${API}/menus/ingest`, { method: "POST", body, credentials: "same-origin" });
  return readJson(res);
}

export async function updateDishField(
  menuId: string,
  versionId: string,
  dishId: string,
  field: string,
  value: string | number | string[],
): Promise<MenuIngestResult> {
  const res = await fetch(`${API}/menus/${menuId}/versions/${versionId}/dishes/${dishId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
  return readJson(res);
}

export async function confirmMenu(menuId: string, versionId: string): Promise<MenuIngestResult> {
  const res = await fetch(`${API}/menus/${menuId}/versions/${versionId}/confirm`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getMenus(): Promise<{ menus: { id: string; name: string; status: string }[] }> {
  const res = await fetch(`${API}/menus`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export type PairingSlot = {
  id: string;
  slot: string;
  status: string;
  sku_id: string | null;
  category: string;
  name: string;
  producer: string;
  region: string;
  style: string;
  rationale: string;
  server_script: string;
  confidence: string;
  price_tier: string;
  glass_price: number;
  bottle_price: number;
  currency: string;
  gap: string;
};

export type PairingOption = {
  sku_id: string;
  name: string;
  producer: string;
  category: string;
  style: string;
};

export type PairingDish = {
  id: string;
  stable_id: string;
  name: string;
  dish: string;
  course: string;
  flavor_profile: string;
  price: number;
  currency: string;
  needs_repairing: boolean;
  options: PairingOption[];
  pairings: PairingSlot[];
};

export type PairingGridResult = {
  menu_id: string;
  menu_name: string;
  dishes: PairingDish[];
};

export async function pairMenu(menuId: string): Promise<PairingGridResult> {
  const res = await fetch(`${API}/menus/${menuId}/pair`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function getPairings(menuId: string): Promise<PairingGridResult> {
  const res = await fetch(`${API}/menus/${menuId}/pairings`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function pinPairing(menuId: string, pairingId: string): Promise<PairingGridResult> {
  const res = await fetch(`${API}/menus/${menuId}/pairings/${pairingId}/pin`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function rejectPairing(menuId: string, pairingId: string): Promise<PairingGridResult> {
  const res = await fetch(`${API}/menus/${menuId}/pairings/${pairingId}/reject`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function swapPairing(menuId: string, pairingId: string, skuId: string): Promise<PairingGridResult> {
  const res = await fetch(`${API}/menus/${menuId}/pairings/${pairingId}/swap`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sku_id: skuId }),
  });
  return readJson(res);
}

export async function getInventory() {
  const res = await fetch(`${API}/inventory`, { cache: "no-store" });
  return res.json();
}

export async function patchStock(sku: string, on_hand: number) {
  const res = await fetch(`${API}/inventory/${sku}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ on_hand }),
  });
  return res.json();
}

export async function getTraining() {
  const res = await fetch(`${API}/training`, { cache: "no-store" });
  return res.json();
}

export async function getTastings() {
  const res = await fetch(`${API}/tastings`, { cache: "no-store" });
  return res.json();
}

export async function getLists() {
  const res = await fetch(`${API}/lists`, { cache: "no-store" });
  return res.json();
}

export type ListImportRow = {
  line: number;
  status: "match" | "new" | "error";
  action: string;
  message: string;
  section: string;
  name: string;
  producer: string;
  category: string;
  vintage: string;
  bottle_size: string;
};

export type TastingNote = {
  id: string;
  product_id: string;
  product_name: string;
  producer: string;
  server_hook: string;
  guest_description: string;
  technical_note: string;
  body: string;
  acidity: string;
  tannin: string;
  sweetness: string;
  oak: string;
  intensity: string;
  aroma_families: string[];
  source: string;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  has_tech_sheet: boolean;
  created_at: string;
};

export type ServiceCardRecord = {
  id: string;
  product_id: string;
  product_name: string;
  tasting_note_id: string;
  serving_temperature: string;
  glassware: string;
  decanting: string;
  pour_size: string;
  source: string;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
};

export type TastingDraft = {
  note: TastingNote;
  service_card: ServiceCardRecord;
};

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res.json();
}

export async function getTastingNotes(productId: string): Promise<{ notes: TastingNote[] }> {
  const res = await fetch(`${API}/products/${productId}/notes`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getServiceCards(productId: string): Promise<{ service_cards: ServiceCardRecord[] }> {
  const res = await fetch(`${API}/products/${productId}/service-cards`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function draftTastingNote(productId: string, techSheet: string, file: File | null): Promise<TastingDraft> {
  const body = new FormData();
  body.set("tech_sheet", techSheet);
  if (file) body.set("file", file);
  const res = await fetch(`${API}/products/${productId}/notes/draft`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function updateTastingNote(
  productId: string,
  noteId: string,
  body: Partial<Pick<TastingNote, "server_hook" | "guest_description" | "technical_note" | "body" | "acidity" | "tannin" | "sweetness" | "oak" | "intensity" | "aroma_families">>,
): Promise<TastingNote> {
  const res = await fetch(`${API}/products/${productId}/notes/${noteId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function approveTastingNote(productId: string, noteId: string): Promise<TastingNote> {
  const res = await fetch(`${API}/products/${productId}/notes/${noteId}/approve`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function updateServiceCard(
  productId: string,
  cardId: string,
  body: Partial<Pick<ServiceCardRecord, "serving_temperature" | "glassware" | "decanting" | "pour_size">>,
): Promise<ServiceCardRecord> {
  const res = await fetch(`${API}/products/${productId}/service-cards/${cardId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function approveServiceCard(productId: string, cardId: string): Promise<ServiceCardRecord> {
  const res = await fetch(`${API}/products/${productId}/service-cards/${cardId}/approve`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export type ListImportItem = {
  section: string;
  name: string;
  producer: string;
  vintage: string;
  bottle_size: string;
  category: string;
  pour_price: number;
  bottle_price: number;
  cost: number;
  currency: string;
  product_id?: string;
};

export type ListImportResult = {
  mode: "preview" | "confirmed";
  currency: string;
  matched: number;
  new: number;
  new_products: number;
  new_variants: number;
  errors: number;
  rows: ListImportRow[];
  list?: {
    id: string;
    name: string;
    currency: string;
    item_count: number;
    source_filename: string;
    items: ListImportItem[];
  };
};

export async function importList(file: File, confirm: boolean): Promise<ListImportResult> {
  const body = new FormData();
  body.set("file", file);
  body.set("confirm", confirm ? "true" : "false");
  const res = await fetch(`${API}/lists/import`, { method: "POST", body, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res.json();
}

export async function getSampleMenu() {
  const res = await fetch(`${API}/fixtures/sample-menu`, { cache: "no-store" });
  return res.json();
}

export type LlmSettings = {
  configured: boolean;
  stored: boolean;
  provider: string | null;
  model: string | null;
  key_hint: string | null;
  demo_mode: boolean;
  demo_forced: boolean;
  source: string;
  label: string;
  warning: string;
  default_models: Record<string, string>;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function notifyStatusChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("madira-status"));
  }
}

async function errorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    if (typeof data.detail === "string" && data.detail) return data.detail;
  } catch {
    // The body was not JSON.
  }
  return text || `Request failed (${res.status})`;
}

async function readSettings(res: Response): Promise<LlmSettings> {
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res.json();
}

export async function getLlmSettings(): Promise<LlmSettings> {
  const res = await fetch(`${API}/settings/llm`, { cache: "no-store", credentials: "same-origin" });
  return readSettings(res);
}

export async function saveLlmSettings(body: {
  provider: string;
  model: string;
  api_key: string;
}): Promise<LlmSettings> {
  const res = await fetch(`${API}/settings/llm`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readSettings(res);
}

export type Account = {
  name: string;
  email: string;
  picture: string;
};

export async function getAuthConfig(): Promise<{ configured: boolean }> {
  const res = await fetch(`${API}/auth/config`, { cache: "no-store" });
  if (!res.ok) throw new Error("auth config failed");
  const data = (await res.json()) as { configured?: boolean };
  return { configured: data.configured === true };
}

export async function getAccount(): Promise<Account | null> {
  try {
    const res = await fetch(`${API}/auth/me`, { cache: "no-store", credentials: "same-origin" });
    if (!res.ok) return null;
    const data = (await res.json()) as { user?: Partial<Account> | null };
    if (!data.user || typeof data.user !== "object") return null;
    return {
      name: typeof data.user.name === "string" ? data.user.name : "",
      email: typeof data.user.email === "string" ? data.user.email : "",
      picture: typeof data.user.picture === "string" ? data.user.picture : "",
    };
  } catch {
    return null;
  }
}

export async function signOutAccount(): Promise<boolean> {
  try {
    const res = await fetch(`${API}/auth/logout`, { method: "POST", credentials: "same-origin" });
    return res.ok;
  } catch {
    return false;
  }
}

export function notifyAuthChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("madira-auth"));
  }
}

export type { AuditChain, AuditEventRow };

export type VaultDocument = {
  id: string;
  doc_type: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  linked_entity_type: string;
  linked_entity_id: string | null;
  uploaded_by_user_id: string | null;
  created_at: string;
};

export type RetentionPolicy = {
  document_retention_years: number;
  can_edit: boolean;
};

export async function getAuditEvents(filters?: {
  entity_type?: string;
  action?: string;
}): Promise<{ events: AuditEventRow[]; chain: AuditChain }> {
  const params = new URLSearchParams();
  if (filters?.entity_type) params.set("entity_type", filters.entity_type);
  if (filters?.action) params.set("action", filters.action);
  const query = params.toString();
  const res = await fetch(`${API}/compliance/audit-events${query ? `?${query}` : ""}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function listDocuments(): Promise<{ documents: VaultDocument[] }> {
  const res = await fetch(`${API}/compliance/documents`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function uploadDocument(input: {
  file: File;
  doc_type: string;
  linked_entity_type?: string;
  linked_entity_id?: string;
}): Promise<{ document: VaultDocument }> {
  const body = new FormData();
  body.set("file", input.file);
  body.set("doc_type", input.doc_type);
  if (input.linked_entity_type) body.set("linked_entity_type", input.linked_entity_type);
  if (input.linked_entity_id) body.set("linked_entity_id", input.linked_entity_id);
  const res = await fetch(`${API}/compliance/documents`, { method: "POST", body, credentials: "same-origin" });
  return readJson(res);
}

export async function getRetention(): Promise<RetentionPolicy> {
  const res = await fetch(`${API}/compliance/retention`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function updateRetention(years: number): Promise<RetentionPolicy> {
  const res = await fetch(`${API}/compliance/retention`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_retention_years: years }),
  });
  return readJson(res);
}

export async function deleteLlmSettings(): Promise<LlmSettings> {
  const res = await fetch(`${API}/settings/llm`, { method: "DELETE", credentials: "same-origin" });
  return readSettings(res);
}
