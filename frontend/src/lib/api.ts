import type { AuditChain, AuditEventRow } from "@/a2ui/auditTableSchema";
import { readCachedJson } from "@/lib/offline";
import type { LookupPack } from "@/lib/lookupOffline";

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

export type CellarLocation = {
  id: string;
  name: string;
  kind: string;
  notes: string;
};

export type StockLocation = {
  location_id: string;
  location_name: string;
  quantity: number;
  valuation_cents: number;
};

export type StockItem = {
  sku: string;
  name: string;
  on_hand: number;
  par: number;
  low: boolean;
  unit: string;
  depletion_30d: number;
  valuation_cents: number;
  currency: string;
  locations: StockLocation[];
};

export type CellarBin = {
  id: string;
  location_id: string;
  location_name: string;
  code: string;
  label: string;
  qr_payload: string;
};

export type StockMovementRow = {
  id: string;
  sku: string;
  name: string;
  location_name: string;
  bin_code: string;
  quantity: number;
  movement_type: string;
  reason: string;
  created_at: string;
};

export type BinLabel = {
  bin_id: string;
  code: string;
  label: string;
  qr_payload: string;
  svg: string;
};

export async function getCellar(): Promise<{ items: StockItem[]; locations: CellarLocation[] }> {
  const res = await fetch(`${API}/inventory`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function listLocations(): Promise<{ locations: CellarLocation[] }> {
  const res = await fetch(`${API}/inventory/locations`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createLocation(input: { name: string; kind: string; notes?: string }) {
  const res = await fetch(`${API}/inventory/locations`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function listBins(): Promise<{ bins: CellarBin[] }> {
  const res = await fetch(`${API}/inventory/bins`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createBin(input: { location_id: string; code: string; label?: string }) {
  const res = await fetch(`${API}/inventory/bins`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function getBinLabel(binId: string): Promise<BinLabel> {
  const res = await fetch(`${API}/inventory/bins/${binId}/qr?format=json`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function listMovements(): Promise<{ movements: StockMovementRow[] }> {
  const res = await fetch(`${API}/inventory/movements?limit=80`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function postMovement(input: {
  sku: string;
  location_id: string;
  quantity: number;
  movement_type: string;
  reason?: string;
}) {
  const res = await fetch(`${API}/inventory/movements`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function postTransfer(input: {
  sku: string;
  from_location_id: string;
  to_location_id: string;
  quantity: number;
  reason?: string;
}) {
  const res = await fetch(`${API}/inventory/transfers`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export type CountSessionRecord = {
  id: string;
  location_id: string;
  location_name: string;
  status: string;
  notes: string;
};

export type CountReport = {
  session: CountSessionRecord;
  lines: {
    id: string;
    sku: string;
    name: string;
    counted_quantity: number;
    expected_quantity: number | null;
    device_id: string;
    bin_code: string;
    counted_at: string | null;
  }[];
  variance_lines: {
    sku: string;
    name: string;
    counted_quantity: number | null;
    expected_quantity: number;
    variance: number | null;
    variance_value_cents: number | null;
    unit_cost_cents: number;
  }[];
  conflicts: {
    sku: string;
    readings: { device_id: string; counted_quantity: number; counted_at: string | null }[];
    resolved: boolean;
    resolved_quantity: number | null;
  }[];
  movements?: { id: string; sku: string; quantity: number; movement_type: string }[];
};

export async function listCountSessions(): Promise<{ sessions: CountSessionRecord[] }> {
  const res = await fetch(`${API}/inventory/counts`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function startCountSession(locationId: string, notes = ""): Promise<CountSessionRecord> {
  const res = await fetch(`${API}/inventory/counts`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ location_id: locationId, notes }),
  });
  return readJson(res);
}

export async function getCountSession(sessionId: string): Promise<CountReport> {
  const res = await fetch(`${API}/inventory/counts/${sessionId}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function syncCountLines(
  sessionId: string,
  entries: {
    client_mutation_id: string;
    device_id: string;
    sku: string;
    counted_quantity: number;
    counted_at: string;
    bin_qr?: string;
    notes?: string;
  }[],
) {
  const res = await fetch(`${API}/inventory/counts/${sessionId}/sync`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entries }),
  });
  return readJson(res);
}

export async function submitCountSession(sessionId: string): Promise<CountReport> {
  const res = await fetch(`${API}/inventory/counts/${sessionId}/submit`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function resolveCountConflict(sessionId: string, sku: string, resolvedQuantity: number) {
  const res = await fetch(`${API}/inventory/counts/${sessionId}/conflicts/${encodeURIComponent(sku)}/resolve`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolved_quantity: resolvedQuantity }),
  });
  return readJson<CountReport>(res);
}

export async function approveCountSession(sessionId: string): Promise<CountReport> {
  const res = await fetch(`${API}/inventory/counts/${sessionId}/approve`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export type ParProposalRecord = {
  id: string;
  sku: string;
  name: string;
  current_par: number;
  proposed_par: number;
  depletion_30d: number;
  rationale: string;
  status: string;
};

export async function listParProposals(status = "pending"): Promise<{ proposals: ParProposalRecord[] }> {
  const res = await fetch(`${API}/inventory/par-proposals?status=${encodeURIComponent(status)}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function generateParProposals(): Promise<{ proposals: ParProposalRecord[] }> {
  const res = await fetch(`${API}/inventory/par-proposals/generate`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lead_time_days: 7, safety_days: 4, proposed_by: "cellar-manager" }),
  });
  return readJson(res);
}

export async function acceptParProposal(proposalId: string): Promise<{ proposal: ParProposalRecord }> {
  const res = await fetch(`${API}/inventory/par-proposals/${proposalId}/accept`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function rejectParProposal(proposalId: string): Promise<{ proposal: ParProposalRecord }> {
  const res = await fetch(`${API}/inventory/par-proposals/${proposalId}/reject`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export type TrainingLesson = {
  id: string;
  slug: string;
  title: string;
  body: string;
  position: string;
  status: string;
  can_author: boolean;
  quiz_id: string | null;
  standards: { id: string; slug: string; title: string }[];
  bottles: { sku_id: string; name: string }[];
};

export type TrainingLessons = {
  role: string;
  name: string;
  position: string | null;
  can_author: boolean;
  lessons: TrainingLesson[];
  drafts: TrainingLesson[];
};

export type TrainingQuiz = {
  id: string;
  lesson_id?: string | null;
  title: string;
  questions: { id: string; prompt: string; choices: string[]; kind?: string }[];
  score?: number | null;
  score_bp?: number | null;
  correct?: number | null;
  total?: number | null;
  review?: { id: string; prompt: string; selected: number; ok: boolean; explain: string }[];
  next_review_at?: string | null;
  next_review_on?: string | null;
};

export type DueReview = {
  quiz_id: string;
  quiz_title: string;
  question_id: string;
  prompt: string;
  box: number;
  due_at: string;
  due_on: string;
  last_result: string;
};

export type ServiceStandard = {
  id: string;
  slug: string;
  topic: string;
  title: string;
  body: string;
  version: number;
  is_default: boolean;
  updated_at: string;
};

export type DemoPersona = {
  slug: string;
  name: string;
  role: string;
  position: string | null;
  email: string;
};

export async function getTrainingLessons(): Promise<TrainingLessons> {
  const res = await fetch(`${API}/training/lessons`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function draftTrainingLesson(position: string): Promise<TrainingLesson> {
  const res = await fetch(`${API}/training/lessons/draft`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position }),
  });
  return readJson(res);
}

export async function approveLesson(lessonId: string): Promise<TrainingLesson> {
  const res = await fetch(`${API}/training/lessons/${lessonId}/approve`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function editLesson(lessonId: string, patch: { title?: string; body?: string; position?: string }): Promise<TrainingLesson> {
  const res = await fetch(`${API}/training/lessons/${lessonId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return readJson(res);
}

export async function getQuiz(quizId: string): Promise<TrainingQuiz> {
  const res = await fetch(`${API}/training/quizzes/${quizId}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function submitQuizAttempt(quizId: string, answers: number[]): Promise<TrainingQuiz> {
  const res = await fetch(`${API}/training/quizzes/${quizId}/attempts`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  return readJson(res);
}

export async function getDueReviews(): Promise<{ reviews: DueReview[] }> {
  const res = await fetch(`${API}/training/reviews/due`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export type RoleplayTurn = { role: "guest" | "staff"; text: string; product_ids?: string[] };
export type RoleplayCriterion = { pass: boolean; evidence: string };
export type RoleplaySession = {
  id: string;
  persona: string;
  dish_id: string | null;
  dish_name: string;
  status: "open" | "scored";
  transcript: RoleplayTurn[];
  rubric: {
    listened: RoleplayCriterion;
    offered_two_options: RoleplayCriterion;
    described_structure: RoleplayCriterion;
    handled_price: RoleplayCriterion;
  } | null;
  score: number | null;
  started_at: string | null;
  scored_at: string | null;
};
export type RoleplayResponse = { session: RoleplaySession };

export async function startRoleplay(persona: string, dish = ""): Promise<RoleplayResponse> {
  const res = await fetch(`${API}/training/roleplay`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona, dish }),
  });
  return readJson(res);
}

export async function replyRoleplay(sessionId: string, text: string): Promise<RoleplayResponse> {
  const res = await fetch(`${API}/training/roleplay/${sessionId}/reply`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return readJson(res);
}

export async function scoreRoleplay(sessionId: string): Promise<RoleplayResponse> {
  const res = await fetch(`${API}/training/roleplay/${sessionId}/score`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export type TeamMember = {
  membership_id: string;
  user_id: string;
  name: string;
  email: string;
  role: string;
  position: string | null;
};
export type TeamInvite = {
  id: string;
  email: string;
  role: string;
  position: string | null;
  invited_by_user_id: string;
  created_at: string | null;
  accepted_at: string | null;
  revoked_at: string | null;
};
export type TeamRoster = { members: TeamMember[]; invites: TeamInvite[] };
export type TeamPerson = {
  user_id: string;
  name: string;
  email: string;
  role: string;
  position: string | null;
  briefing_ack: { acked: number; published: number; rate_bp: number | null; label: string };
  lessons_done: number;
  quiz_average_bp: number | null;
  quiz_average_label: string;
  roleplay_average_bp: number | null;
  roleplay_average_label: string;
};
export type WeakTopic = { topic: string; correct: number; total: number; accuracy_bp: number; label: string };
export type CertificateRecord = {
  id: string;
  user_id: string;
  name: string;
  kind: string;
  label: string;
  issued_on: string;
  expires_on: string;
  document_id: string | null;
  document_filename: string;
  created_by_user_id: string;
  created_at: string | null;
  days_left: number;
  expired: boolean;
  expiring: boolean;
  due: boolean;
  gap_type: string;
  status_label: string;
};
export type TeamProgress = {
  week: { start: string; end: string };
  people: TeamPerson[];
  weak_topics: WeakTopic[];
  expiring_certificates: CertificateRecord[];
};

export async function getTeam(): Promise<TeamRoster> {
  const res = await fetch(`${API}/team`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getTeamProgress(): Promise<TeamProgress> {
  const res = await fetch(`${API}/team/progress`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function inviteTeamMember(body: { email: string; role: string; position: string | null }): Promise<TeamInvite> {
  const res = await fetch(`${API}/team/invites`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function revokeTeamInvite(inviteId: string): Promise<TeamInvite> {
  const res = await fetch(`${API}/team/invites/${inviteId}/revoke`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function updateTeamMember(userId: string, body: { role: string; position: string | null }): Promise<TeamMember> {
  const res = await fetch(`${API}/team/members/${userId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function removeTeamMember(userId: string): Promise<{ removed: boolean; user_id: string }> {
  const res = await fetch(`${API}/team/members/${userId}`, { method: "DELETE", credentials: "same-origin" });
  return readJson(res);
}

export async function getTeamCertificates(): Promise<{ certificates: CertificateRecord[] }> {
  const res = await fetch(`${API}/team/certificates`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createCertificate(input: {
  userId: string;
  kind: string;
  label: string;
  issuedOn: string;
  expiresOn: string;
  file: File | null;
}): Promise<CertificateRecord> {
  const body = new FormData();
  body.set("user_id", input.userId);
  body.set("kind", input.kind);
  body.set("label", input.label);
  body.set("issued_on", input.issuedOn);
  body.set("expires_on", input.expiresOn);
  if (input.file) body.set("file", input.file);
  const res = await fetch(`${API}/team/certificates`, { method: "POST", credentials: "same-origin", body });
  const payload = await readJson<{ certificate: CertificateRecord }>(res);
  return payload.certificate;
}

export async function deleteCertificate(certificateId: string): Promise<{ removed: boolean }> {
  const res = await fetch(`${API}/team/certificates/${certificateId}`, { method: "DELETE", credentials: "same-origin" });
  return readJson(res);
}

export type BriefingItem = { title: string; detail: string };
export type BriefingCard = { kind: string; title: string; body: string; items: BriefingItem[] };
export type TonightBriefing = {
  id: string;
  service_date: string;
  status: string;
  intro: string;
  cards: BriefingCard[];
  due_review_count: number;
  acknowledged: boolean;
  seconds_to_ack: number | null;
};
export type TonightBoard = {
  service_date: string;
  briefing_hour: number;
  timezone: string;
  available: boolean;
  role: string;
  briefing: TonightBriefing | null;
  low_stock: { sku: string; name: string; on_hand: number; par: number }[];
  storage_alerts: { id: string; zone: string; metric: string; status: string }[];
  deliveries_due: { po_number: string; supplier: string; expected_delivery_date: string | null; status: string }[];
  approvals: { id: string; kind: string; title: string; status: string }[];
  expiring_certificates: {
    id: string;
    user_id: string;
    name: string;
    kind: string;
    label: string;
    issued_on: string;
    expires_on: string;
    days_left: number;
    status_label: string;
  }[];
};
export type LookupHit = {
  name: string;
  producer: string;
  grape: string;
  region: string;
  pairing: string;
  server_script: string;
  flavor_profile: string;
  glassware: string;
  serving_temperature: string;
  pour_size: string;
  stock: number | string;
  price_cents: number;
  currency: string;
};

export async function getTonight(): Promise<TonightBoard> {
  const res = await fetch(`${API}/tonight`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export type TonightEnvelope = {
  role: string;
  available: boolean;
  ready: boolean;
  service_date: string;
  timezone: string;
  briefing_hour: number;
  briefing: TonightBriefing | null;
};

export type { LookupPack };

export async function getTonightBriefing(serviceDate?: string): Promise<TonightEnvelope> {
  const params = serviceDate ? `?service_date=${encodeURIComponent(serviceDate)}` : "";
  const path = `${API}/tonight/briefing${params}`;
  try {
    const res = await fetch(path, { cache: "no-store", credentials: "same-origin" });
    if (res.ok) return res.json();
  } catch {
    // The service worker or the page cache may still have the last briefing.
  }
  const cached = await readCachedJson<TonightEnvelope>(path);
  if (cached) return cached;
  throw new Error("Tonight's briefing is not on this phone yet.");
}

export async function getLookupPack(): Promise<LookupPack> {
  const path = `${API}/lookup/pack`;
  try {
    const res = await fetch(path, { cache: "no-store", credentials: "same-origin" });
    if (res.ok) return res.json();
  } catch {
    // Offline lookup uses the pack captured on the last visit.
  }
  const cached = await readCachedJson<LookupPack>(path);
  if (cached) return cached;
  throw new Error("The floor list is not on this phone yet.");
}

export async function acknowledgeBriefing(id: string, secondsToAck: number): Promise<TonightBriefing> {
  const res = await fetch(`${API}/tonight/briefing/${id}/ack`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seconds_to_ack: secondsToAck }),
  });
  return readJson(res);
}

export type BriefingReportUser = {
  user_id: string;
  name: string;
  acknowledged: boolean;
  seconds_to_ack: number | null;
};

export type BriefingReportDay = {
  service_date: string;
  briefing_id: string | null;
  status: string | null;
  acknowledged_count: number;
  user_count: number;
  users: BriefingReportUser[];
};

export type BriefingReport = {
  start: string;
  end: string;
  days: BriefingReportDay[];
};

export async function getBriefingReport(start: string, end: string): Promise<BriefingReport> {
  const params = new URLSearchParams({ start, end });
  const res = await fetch(`${API}/tonight/briefing/report?${params}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function lookupFloor(query: string): Promise<{ query: string; results: LookupHit[] }> {
  const res = await fetch(`${API}/lookup?q=${encodeURIComponent(query)}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getStandards(): Promise<{ can_author: boolean; standards: ServiceStandard[] }> {
  const res = await fetch(`${API}/training/standards`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function saveStandard(standard: { slug: string; title: string; body: string; topic?: string }): Promise<ServiceStandard> {
  const res = await fetch(`${API}/training/standards`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(standard),
  });
  return readJson(res);
}

export async function resetStandard(slug: string): Promise<ServiceStandard> {
  const res = await fetch(`${API}/training/standards/${slug}/reset`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getDemoPersonas(): Promise<{ active: string; personas: DemoPersona[] } | null> {
  const res = await fetch(`${API}/auth/demo-personas`, { cache: "no-store", credentials: "same-origin" });
  if (!res.ok) return null;
  return res.json();
}

export async function setDemoPersona(slug: string): Promise<void> {
  const res = await fetch(`${API}/auth/demo-persona`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug }),
  });
  if (!res.ok) throw new Error("The demo persona could not be changed.");
}

export async function getTastings() {
  const res = await fetch(`${API}/tastings`, { cache: "no-store" });
  return res.json();
}

export async function getLists(): Promise<{ lists: BeverageListDetail[] }> {
  const res = await fetch(`${API}/lists`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
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
    if (data.detail && typeof data.detail === "object" && "message" in data.detail) {
      const message = (data.detail as { message?: unknown }).message;
      if (typeof message === "string" && message) return message;
    }
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

export type SupplierContactRow = {
  id: string;
  supplier_id: string;
  name: string;
  role: string | null;
  email: string;
  phone: string | null;
  is_primary: boolean;
};

export type SupplierRow = {
  id: string;
  name: string;
  kind: string;
  contact_email: string;
  account_number: string | null;
  order_minimum_cents: number;
  default_case_size: number;
  delivery_days: string[];
  lead_time_days: number;
  payment_terms: string | null;
  notes: string;
  contacts: SupplierContactRow[];
};

export type PurchaseLine = {
  id: string;
  sku: string;
  name: string;
  product_name: string;
  case_size: number;
  cases_ordered: number;
  quantity_ordered: number;
  quantity_received: number;
  unit_cost_cents: number;
  line_total_cents: number;
  vintage: string | null;
};

export type PurchaseApproval = {
  id: string;
  decision: string;
  required_role: string;
  comment: string | null;
  decided_at: string | null;
};

export type PurchaseOrderRow = {
  id: string;
  po_number: string | null;
  status: string;
  supplier_id: string;
  supplier: string;
  contact: SupplierContactRow | null;
  expected_delivery_date: string | null;
  subtotal_cents: number;
  order_minimum_cents: number;
  minimum_met: boolean;
  shortfall_cents: number;
  pdf_document_id: string | null;
  sent_via: string | null;
  lines: PurchaseLine[];
  approval: PurchaseApproval;
};

export async function listProcurementSuppliers(): Promise<{ suppliers: SupplierRow[] }> {
  const res = await fetch(`${API}/procurement/suppliers`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createProcurementSupplier(body: {
  name: string;
  default_case_size: number;
  order_minimum_cents: number;
  delivery_days: string[];
  lead_time_days: number;
  payment_terms?: string;
}): Promise<{ supplier: SupplierRow }> {
  const res = await fetch(`${API}/procurement/suppliers`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function addSupplierContact(
  supplierId: string,
  body: { name: string; email: string; role?: string; phone?: string; is_primary?: boolean },
): Promise<{ contact: SupplierContactRow }> {
  const res = await fetch(`${API}/procurement/suppliers/${supplierId}/contacts`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function listLifecycleOrders(): Promise<{ orders: PurchaseOrderRow[] }> {
  const res = await fetch(`${API}/procurement/orders`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createLifecycleOrder(body: {
  supplier_id: string;
  notes?: string;
  lines: { sku: string; product_name: string; bottles: number; unit_cost_cents: number }[];
}): Promise<PurchaseOrderRow> {
  const res = await fetch(`${API}/procurement/orders`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function draftLifecycleOrders(): Promise<{ orders: PurchaseOrderRow[] }> {
  const res = await fetch(`${API}/procurement/orders/draft-from-reorder`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function decidePurchaseOrder(
  poId: string,
  decision: "approve" | "reject",
  comment: string,
): Promise<PurchaseOrderRow> {
  const res = await fetch(`${API}/procurement/orders/${poId}/${decision}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  return readJson(res);
}

export async function sendPurchaseOrder(poId: string): Promise<PurchaseOrderRow> {
  const res = await fetch(`${API}/procurement/orders/${poId}/send`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function closePurchaseOrder(poId: string): Promise<PurchaseOrderRow> {
  const res = await fetch(`${API}/procurement/orders/${poId}/close`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function cancelPurchaseOrder(poId: string): Promise<PurchaseOrderRow> {
  const res = await fetch(`${API}/procurement/orders/${poId}/cancel`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export type InvoiceLine = {
  sku: string;
  product_name?: string;
  quantity: number;
  unit_cost_cents: number;
  vintage?: string | null;
  po_line_id?: string | null;
};

export type InvoiceRecord = {
  id: string;
  purchase_order_id: string | null;
  invoice_number: string;
  invoice_date: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  currency: string;
  document_id: string;
  filename: string;
  sha256: string;
  content_type: string;
  extracted_lines: InvoiceLine[];
  extraction_mode: string;
  status: string;
};

export type ReceiptLineRecord = {
  id: string;
  po_line_id: string | null;
  sku: string;
  product_name: string;
  ordered_qty: number;
  invoiced_qty: number | null;
  counted_qty: number;
  ordered_unit_cost_cents: number;
  invoiced_unit_cost_cents: number | null;
  ordered_vintage: string | null;
  received_vintage: string | null;
  bin_id: string | null;
  flags: string[];
  resolution_note: string | null;
  cost_delta_cents: number;
};

export type DiscrepancySummary = {
  has_discrepancies: boolean;
  counts: Record<string, number>;
  cost_delta_cents: number;
  lines: { sku: string; flags: string[]; cost_delta_cents: number }[];
};

export type ReceiptRecord = {
  id: string;
  purchase_order_id: string;
  po_number: string | null;
  supplier: string;
  purchase_order_status: string | null;
  invoice_id: string | null;
  status: string;
  discrepancy_summary: DiscrepancySummary;
  notes: string | null;
  lines: ReceiptLineRecord[];
  a2ui_operations?: unknown[];
};

export async function uploadInvoice(
  poId: string,
  input: { file: File; invoice_number: string; invoice_date: string; tax_cents?: number; lines?: InvoiceLine[] },
): Promise<InvoiceRecord> {
  const body = new FormData();
  body.set("file", input.file);
  body.set("invoice_number", input.invoice_number);
  body.set("invoice_date", input.invoice_date);
  if (input.tax_cents != null) body.set("tax_cents", String(input.tax_cents));
  if (input.lines) body.set("lines_json", JSON.stringify(input.lines));
  const res = await fetch(`${API}/procurement/orders/${poId}/invoices`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function stageReceipt(
  poId: string,
  input: {
    invoice_id?: string | null;
    notes?: string | null;
    lines: {
      po_line_id?: string | null;
      sku: string;
      counted_qty: number;
      received_vintage?: string | null;
      bin_id?: string | null;
    }[];
  },
): Promise<ReceiptRecord> {
  const res = await fetch(`${API}/procurement/orders/${poId}/receipts`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function acceptReceipt(
  receiptId: string,
  input: { acknowledge_discrepancies: boolean; notes?: string | null },
): Promise<ReceiptRecord> {
  const res = await fetch(`${API}/procurement/receipts/${receiptId}/accept`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function deleteLlmSettings(): Promise<LlmSettings> {
  const res = await fetch(`${API}/settings/llm`, { method: "DELETE", credentials: "same-origin" });
  return readSettings(res);
}

export type AffectedSku = {
  sku: string;
  product_name: string;
  bin_code: string;
  on_hand: number;
};

export type ZoneReading = {
  id: string;
  zone_id?: string;
  temp_c: number;
  humidity_pct: number;
  source?: string;
  recorded_at?: string | null;
  notes?: string | null;
  in_range?: boolean;
};

export type ZoneExcursion = {
  id: string;
  zone_id?: string;
  reading_id?: string;
  metric: string;
  status: string;
  measured_temp_c?: number;
  measured_humidity_pct?: number;
  affected_skus: AffectedSku[];
  resolution_note?: string | null;
  created_at?: string | null;
};

export type StorageZone = {
  id: string;
  name: string;
  location_id?: string | null;
  location_name?: string | null;
  target_temp_min_c: number;
  target_temp_max_c: number;
  target_humidity_min_pct: number;
  target_humidity_max_pct: number;
  notes?: string | null;
  latest_reading?: ZoneReading | null;
  status: string;
  excursion?: ZoneExcursion | null;
};

export async function listStorageZones(): Promise<{ zones: StorageZone[] }> {
  const res = await fetch(`${API}/inventory/storage-zones`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function recordZoneReading(
  zoneId: string,
  tempC: number,
  humidityPct: number,
  notes?: string,
): Promise<{ reading: ZoneReading; excursion: ZoneExcursion | null; zone: StorageZone }> {
  const res = await fetch(`${API}/inventory/storage-zones/${zoneId}/readings`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ temp_c: tempC, humidity_pct: humidityPct, notes: notes || null }),
  });
  return readJson(res);
}

export async function acknowledgeExcursion(excursionId: string, resolutionNote?: string): Promise<{ excursion: ZoneExcursion }> {
  const res = await fetch(`${API}/inventory/excursions/${excursionId}/acknowledge`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolution_note: resolutionNote || null }),
  });
  return readJson(res);
}

export type AuditPackPurchase = {
  supplier: string;
  po_count: number;
  invoice_count: number;
  total_invoiced_cents: number;
  total_received_value_cents: number;
};

export type AuditPackGap = {
  purchase_order_id: string;
  po_number: string;
  supplier: string;
  status: string;
  reason: string;
};

export type AuditPackPreview = {
  venue: { id: string; name: string };
  start_date: string;
  end_date: string;
  purchases_by_supplier: AuditPackPurchase[];
  invoice_register: { invoice_number: string; total_cents: number; status: string }[];
  missing_invoice_gaps: AuditPackGap[];
  inventory_valuation: {
    start_bottles: number;
    start_value_cents: number;
    end_bottles: number;
    end_value_cents: number;
  };
  variance_and_shrinkage: { quantity_delta: number; cost_impact_cents: number; count_sessions: unknown[] };
  comp_breakage_waste: { cost_impact_cents: number; movements: unknown[] };
  retention: { document_retention_years: number; retain_until: string };
  chain: { valid: boolean; checked: number; head_hash: string | null };
};

export async function previewAuditPack(startDate: string, endDate: string): Promise<AuditPackPreview> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  const res = await fetch(`${API}/compliance/audit-pack/preview?${params}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export type PricingRule = {
  id: string | null;
  category: string;
  cost_min_cents: number;
  cost_max_cents: number | null;
  bottle_multiple: number;
  glass_pours_per_bottle: number;
  glass_multiple: number;
  round_to_cents: number;
};

export type ListItemRecord = {
  id: string;
  sku_id: string;
  product_id: string | null;
  list_id: string;
  section: string;
  section_id: string | null;
  position: number;
  category: string;
  name: string;
  producer: string;
  region: string;
  style: string;
  vintage: string;
  cost?: number;
  pour_price: number;
  bottle_price: number;
  currency: string;
  margin_pct?: number;
  beverage_cost_pct?: number;
  rule_bottle_price?: number;
  rule_glass_price?: number;
  line_cost?: number;
  band: string;
};

export type ListSectionRecord = {
  id: string;
  name: string;
  position: number;
  budget_share_pct: number | null;
  spend?: number;
  item_count: number;
  margin_pct?: number;
  beverage_cost_pct?: number;
};

export type CoverageCell = {
  category: string;
  style: string;
  band: string;
  status: string;
  product_id: string | null;
  sku_id: string | null;
  name: string;
  dish_id: string | null;
  dish_name: string;
};

export type ListCandidate = {
  sku_id: string;
  product_id: string;
  name: string;
  category: string;
  style: string;
  band: string;
  cost?: number;
};

export type HealthFlag = {
  code: string;
  message: string;
  dish_id: string | null;
  item_id: string | null;
  sku_id: string | null;
  section: string;
};

export type BeverageListDetail = {
  id: string;
  list_id: string;
  name: string;
  budget: number;
  spent: number;
  remaining: number;
  currency: string;
  target_margin: number;
  target_beverage_cost_pct: number | null;
  concept: string;
  price_tier: string;
  notes: string;
  item_count: number;
  items: ListItemRecord[];
  sections: ListSectionRecord[];
  cells: CoverageCell[];
  suggestions: CoverageCell[];
  gaps: string[];
  health: { list_id: string; flags: HealthFlag[] };
  candidates: ListCandidate[];
  bottles: number;
  capacity_bottles: number | null;
};

export async function curateList(body: {
  budget: number;
  target_margin: number;
  target_beverage_cost_pct?: number | null;
  concept?: string;
  price_tier?: string;
  name?: string;
}): Promise<BeverageListDetail> {
  const res = await fetch(`${API}/lists/curate`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function addListItem(listId: string, skuId: string, section = ""): Promise<BeverageListDetail> {
  const res = await fetch(`${API}/lists/${listId}/items`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sku_id: skuId, section }),
  });
  return readJson(res);
}

export async function updateListItem(
  listId: string,
  itemId: string,
  patch: { reprice?: boolean; pour_price?: number; bottle_price?: number; position?: number; section?: string },
): Promise<BeverageListDetail> {
  const res = await fetch(`${API}/lists/${listId}/items/${itemId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return readJson(res);
}

export async function deleteListItem(listId: string, itemId: string): Promise<BeverageListDetail> {
  const res = await fetch(`${API}/lists/${listId}/items/${itemId}`, {
    method: "DELETE",
    credentials: "same-origin",
  });
  return readJson(res);
}

export type ListDiffRow = {
  sku_id: string;
  name: string;
  section: string;
  position: number;
  bottle_price_cents: number;
  glass_price_cents: number;
  currency: string;
  previous_bottle_price_cents?: number;
  previous_glass_price_cents?: number;
  previous_section?: string;
  previous_position?: number;
};

export type ListDiff = {
  added: ListDiffRow[];
  removed: ListDiffRow[];
  repriced: ListDiffRow[];
  moved: ListDiffRow[];
};

export type ListVersionRecord = {
  id: string;
  list_id: string;
  list_name: string;
  number: number;
  status: string;
  can_submit: boolean;
  can_decide: boolean;
  public_path: string | null;
  public_token: string | null;
  approval: {
    id?: string;
    decision?: string;
    required_role?: string;
    comment?: string | null;
    decided_at?: string | null;
  } | null;
  diff: ListDiff;
};

export type PublicListItem = {
  name: string;
  detail: string;
  bottle_price_cents: number;
  glass_price_cents: number;
  currency: string;
};

export type PublicList = {
  venue_name: string;
  published_at: string | null;
  list: {
    list_name: string;
    number: number;
    currency: string;
    sections: { name: string; items: PublicListItem[] }[];
  };
};

export async function listVersions(listId: string): Promise<{ list_id: string; can_submit: boolean; versions: ListVersionRecord[] }> {
  const res = await fetch(`${API}/lists/${listId}/versions`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createListVersion(listId: string): Promise<ListVersionRecord> {
  const res = await fetch(`${API}/lists/${listId}/versions`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function submitListVersion(versionId: string): Promise<ListVersionRecord> {
  const res = await fetch(`${API}/lists/versions/${versionId}/submit`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function decideListVersion(
  versionId: string,
  decision: "approve" | "reject",
  comment = "",
): Promise<ListVersionRecord> {
  const res = await fetch(`${API}/lists/versions/${versionId}/${decision}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  return readJson(res);
}

export async function revokePublicList(versionId: string): Promise<ListVersionRecord> {
  const res = await fetch(`${API}/lists/versions/${versionId}/revoke-public`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export function listQrPath(versionId: string) {
  return `${API}/lists/versions/${versionId}/qr.png`;
}

export async function getPublicList(token: string): Promise<PublicList> {
  const res = await fetch(`${API}/public/lists/${encodeURIComponent(token)}`, { cache: "no-store" });
  return readJson(res);
}

export function auditPackExportPath(startDate: string, endDate: string, format: "zip" | "journal_csv" | "summary_pdf" | "summary_csv") {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate, format });
  return `${API}/compliance/audit-pack/export?${params}`;
}
