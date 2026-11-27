import { CSRF_HEADER, ensureCsrfToken } from "@/lib/csrf";
import { readCachedJson } from "@/lib/offline";

import type {
  Account,
  AffectedSku,
  AllocationEnvelope,
  AllocationRecord,
  AuditChain,
  AuditEventList,
  AuditEventRow,
  AuditPackGap,
  AuditPackPreview,
  AuditPackPurchase,
  AuditorQuery,
  AuthConfig,
  BeverageListDetail,
  BinLabel,
  BinList,
  BriefingCard,
  BriefingItem,
  BriefingReport,
  BriefingReportDay,
  BriefingReportUser,
  CatalogChoice,
  CellarBin,
  CellarBoard,
  CellarLocation,
  CertificateList,
  CertificateRecord,
  ContactEnvelope,
  CountReport,
  CountSessionList,
  CountSessionRecord,
  CoverageCell,
  DeletedFlag,
  DeletedId,
  DemoPersona,
  DemoPersonaList,
  DiscrepancySummary,
  DocumentEnvelope,
  DocumentList,
  DueReview,
  DueReviewList,
  HealthFlag,
  InviteDesk,
  InviteGap,
  InviteSlot,
  InvoiceLine,
  InvoiceRecord,
  ListCandidate,
  ListDiff,
  ListDiffRow,
  ListImportItem,
  ListImportResult,
  ListImportRow,
  ListIndex,
  ListItemRecord,
  ListSectionRecord,
  ListVersionIndex,
  ListVersionRecord,
  LlmSettings,
  LocationList,
  LookupHit,
  LookupPack,
  LookupResult,
  MenuDish,
  MenuIngestResult,
  MenuList,
  MenuReview,
  MovementList,
  OfferRecord,
  PairingDish,
  PairingGridResult,
  PairingOption,
  PairingSlot,
  ParProposalEnvelope,
  ParProposalList,
  ParProposalRecord,
  PosCatalog,
  PosCatalogItem,
  PosGapItem,
  PosGapList,
  PosMapping,
  PosMappingEnvelope,
  PosMappingList,
  PosRun,
  PosRunList,
  PosStatus,
  PosSyncResult,
  PriceHistory,
  PricePointRecord,
  PriceSheetApplied,
  PriceSheetEnvelope,
  PriceSheetLine,
  PriceSheetRecord,
  PricingRule,
  ProductList,
  ProfileEnvelope,
  PublicList,
  PublicListItem,
  PurchaseApproval,
  PurchaseLine,
  PurchaseOrderList,
  PurchaseOrderRow,
  ReceiptLineRecord,
  ReceiptRecord,
  ReminderDecision,
  ReminderRecord,
  RemovedMember,
  RepFollowup,
  RepFollowupDraft,
  RepFollowupEnvelope,
  RetentionPolicy,
  RoleplayCriterion,
  RoleplayResponse,
  RoleplaySession,
  RoleplayTurn,
  SampleEnvelope,
  SensorImport,
  SensorImportRow,
  SensorList,
  SensorRecord,
  ServiceCardList,
  ServiceCardRecord,
  ServiceStandard,
  SourcingBrief,
  SourcingBriefEnvelope,
  SourcingBriefItem,
  SourcingBriefList,
  StandardList,
  StockItem,
  StockLocation,
  StockMovementRow,
  StorageZone,
  StorageZoneList,
  SupplierContactRow,
  SupplierDeskPayload,
  SupplierEnvelope,
  SupplierList,
  SupplierProfile,
  SupplierRow,
  TastingCreateResult,
  TastingDraft,
  TastingHistory,
  TastingHistoryRow,
  TastingInvite,
  TastingNote,
  TastingNoteList,
  TastingSessionDetail,
  TastingSessionList,
  TastingSessionRow,
  TeamInvite,
  TeamMember,
  TeamPerson,
  TeamProgress,
  TeamRoster,
  TonightBoard,
  TonightBriefing,
  TonightEnvelope,
  TrainingLesson,
  TrainingLessons,
  TrainingQuiz,
  UsageReport,
  VaultDocument,
  WeakTopic,
  ZoneExcursion,
  ZoneExcursionEnvelope,
  ZoneReading,
  ZoneReadingResult,
} from "./api-types.gen";

export type {
  Account,
  AffectedSku,
  AllocationEnvelope,
  AllocationRecord,
  AuditChain,
  AuditEventList,
  AuditEventRow,
  AuditPackGap,
  AuditPackPreview,
  AuditPackPurchase,
  AuditorQuery,
  AuthConfig,
  BeverageListDetail,
  BinLabel,
  BinList,
  BriefingCard,
  BriefingItem,
  BriefingReport,
  BriefingReportDay,
  BriefingReportUser,
  CatalogChoice,
  CellarBin,
  CellarBoard,
  CellarLocation,
  CertificateList,
  CertificateRecord,
  ContactEnvelope,
  CountReport,
  CountSessionList,
  CountSessionRecord,
  CoverageCell,
  DeletedFlag,
  DeletedId,
  DemoPersona,
  DemoPersonaList,
  DiscrepancySummary,
  DocumentEnvelope,
  DocumentList,
  DueReview,
  DueReviewList,
  HealthFlag,
  InviteDesk,
  InviteGap,
  InviteSlot,
  InvoiceLine,
  InvoiceRecord,
  ListCandidate,
  ListDiff,
  ListDiffRow,
  ListImportItem,
  ListImportResult,
  ListImportRow,
  ListIndex,
  ListItemRecord,
  ListSectionRecord,
  ListVersionIndex,
  ListVersionRecord,
  LlmSettings,
  LocationList,
  LookupHit,
  LookupPack,
  LookupResult,
  MenuDish,
  MenuIngestResult,
  MenuList,
  MenuReview,
  MovementList,
  OfferRecord,
  PairingDish,
  PairingGridResult,
  PairingOption,
  PairingSlot,
  ParProposalEnvelope,
  ParProposalList,
  ParProposalRecord,
  PosCatalog,
  PosCatalogItem,
  PosGapItem,
  PosGapList,
  PosMapping,
  PosMappingEnvelope,
  PosMappingList,
  PosRun,
  PosRunList,
  PosStatus,
  PosSyncResult,
  PriceHistory,
  PricePointRecord,
  PriceSheetApplied,
  PriceSheetEnvelope,
  PriceSheetLine,
  PriceSheetRecord,
  PricingRule,
  ProductList,
  ProfileEnvelope,
  PublicList,
  PublicListItem,
  PurchaseApproval,
  PurchaseLine,
  PurchaseOrderList,
  PurchaseOrderRow,
  ReceiptLineRecord,
  ReceiptRecord,
  ReminderDecision,
  ReminderRecord,
  RemovedMember,
  RepFollowup,
  RepFollowupDraft,
  RepFollowupEnvelope,
  RetentionPolicy,
  RoleplayCriterion,
  RoleplayResponse,
  RoleplaySession,
  RoleplayTurn,
  SampleEnvelope,
  SensorImport,
  SensorImportRow,
  SensorList,
  SensorRecord,
  ServiceCardList,
  ServiceCardRecord,
  ServiceStandard,
  SourcingBrief,
  SourcingBriefEnvelope,
  SourcingBriefItem,
  SourcingBriefList,
  StandardList,
  StockItem,
  StockLocation,
  StockMovementRow,
  StorageZone,
  StorageZoneList,
  SupplierContactRow,
  SupplierDeskPayload,
  SupplierEnvelope,
  SupplierList,
  SupplierProfile,
  SupplierRow,
  TastingCreateResult,
  TastingDraft,
  TastingHistory,
  TastingHistoryRow,
  TastingInvite,
  TastingNote,
  TastingNoteList,
  TastingSessionDetail,
  TastingSessionList,
  TastingSessionRow,
  TeamInvite,
  TeamMember,
  TeamPerson,
  TeamProgress,
  TeamRoster,
  TonightBoard,
  TonightBriefing,
  TonightEnvelope,
  TrainingLesson,
  TrainingLessons,
  TrainingQuiz,
  UsageReport,
  VaultDocument,
  WeakTopic,
  ZoneExcursion,
  ZoneExcursionEnvelope,
  ZoneReading,
  ZoneReadingResult,
};

export const API = "/madira-api";

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (MUTATING.has(method)) {
    const token = await ensureCsrfToken();
    if (token) headers.set(CSRF_HEADER, token);
  }
  return globalThis.fetch(input, {
    ...init,
    credentials: init.credentials ?? "same-origin",
    headers,
  });
}

export async function getStatus() {
  const res = await apiFetch(`${API}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("status failed");
  return res.json();
}

export async function uploadMenu(payload: { text?: string; file?: File }) {
  const body = new FormData();
  if (payload.text) body.set("text", payload.text);
  if (payload.file) body.set("file", payload.file);
  const res = await apiFetch(`${API}/menus/upload`, { method: "POST", body });
  if (!res.ok) throw new Error(await res.text());
  return unwrapJob(await res.json());
}

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
  const res = await apiFetch(`${API}/menus/ingest`, { method: "POST", body, credentials: "same-origin" });
  return unwrapJob(await readJson(res));
}

export async function updateDishField(
  menuId: string,
  versionId: string,
  dishId: string,
  field: string,
  value: string | number | string[],
): Promise<MenuIngestResult> {
  const res = await apiFetch(`${API}/menus/${menuId}/versions/${versionId}/dishes/${dishId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
  return readJson(res);
}

export async function confirmMenu(menuId: string, versionId: string): Promise<MenuIngestResult> {
  const res = await apiFetch(`${API}/menus/${menuId}/versions/${versionId}/confirm`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getMenus(): Promise<MenuList> {
  const res = await apiFetch(`${API}/menus`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function pairMenu(menuId: string): Promise<PairingGridResult> {
  const res = await apiFetch(`${API}/menus/${menuId}/pair`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function getPairings(menuId: string): Promise<PairingGridResult> {
  const res = await apiFetch(`${API}/menus/${menuId}/pairings`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function pinPairing(menuId: string, pairingId: string): Promise<PairingGridResult> {
  const res = await apiFetch(`${API}/menus/${menuId}/pairings/${pairingId}/pin`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function rejectPairing(menuId: string, pairingId: string): Promise<PairingGridResult> {
  const res = await apiFetch(`${API}/menus/${menuId}/pairings/${pairingId}/reject`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function swapPairing(menuId: string, pairingId: string, skuId: string): Promise<PairingGridResult> {
  const res = await apiFetch(`${API}/menus/${menuId}/pairings/${pairingId}/swap`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sku_id: skuId }),
  });
  return readJson(res);
}

export async function getInventory() {
  const res = await apiFetch(`${API}/inventory`, { cache: "no-store" });
  return res.json();
}

export async function patchStock(sku: string, on_hand: number) {
  const res = await apiFetch(`${API}/inventory/${sku}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ on_hand }),
  });
  return res.json();
}

export async function getCellar(): Promise<CellarBoard> {
  const res = await apiFetch(`${API}/inventory`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function listLocations(): Promise<LocationList> {
  const res = await apiFetch(`${API}/inventory/locations`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createLocation(input: { name: string; kind: string; notes?: string }) {
  const res = await apiFetch(`${API}/inventory/locations`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function listBins(): Promise<BinList> {
  const res = await apiFetch(`${API}/inventory/bins`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createBin(input: { location_id: string; code: string; label?: string }) {
  const res = await apiFetch(`${API}/inventory/bins`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function getBinLabel(binId: string): Promise<BinLabel> {
  const res = await apiFetch(`${API}/inventory/bins/${binId}/qr?format=json`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function listMovements(): Promise<MovementList> {
  const res = await apiFetch(`${API}/inventory/movements?limit=80`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function postMovement(input: {
  sku: string;
  location_id: string;
  quantity: number;
  movement_type: string;
  reason?: string;
}) {
  const res = await apiFetch(`${API}/inventory/movements`, {
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
  const res = await apiFetch(`${API}/inventory/transfers`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function listCountSessions(): Promise<CountSessionList> {
  const res = await apiFetch(`${API}/inventory/counts`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function startCountSession(locationId: string, notes = ""): Promise<CountSessionRecord> {
  const res = await apiFetch(`${API}/inventory/counts`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ location_id: locationId, notes }),
  });
  return readJson(res);
}

export async function getCountSession(sessionId: string): Promise<CountReport> {
  const res = await apiFetch(`${API}/inventory/counts/${sessionId}`, { cache: "no-store", credentials: "same-origin" });
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
  const res = await apiFetch(`${API}/inventory/counts/${sessionId}/sync`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entries }),
  });
  return readJson(res);
}

export async function submitCountSession(sessionId: string): Promise<CountReport> {
  const res = await apiFetch(`${API}/inventory/counts/${sessionId}/submit`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function resolveCountConflict(sessionId: string, sku: string, resolvedQuantity: number) {
  const res = await apiFetch(`${API}/inventory/counts/${sessionId}/conflicts/${encodeURIComponent(sku)}/resolve`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolved_quantity: resolvedQuantity }),
  });
  return readJson<CountReport>(res);
}

export async function approveCountSession(sessionId: string): Promise<CountReport> {
  const res = await apiFetch(`${API}/inventory/counts/${sessionId}/approve`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function listParProposals(status = "pending"): Promise<ParProposalList> {
  const res = await apiFetch(`${API}/inventory/par-proposals?status=${encodeURIComponent(status)}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function generateParProposals(): Promise<ParProposalList> {
  const res = await apiFetch(`${API}/inventory/par-proposals/generate`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lead_time_days: 7, safety_days: 4, proposed_by: "cellar-manager" }),
  });
  return readJson(res);
}

export async function acceptParProposal(proposalId: string): Promise<ParProposalEnvelope> {
  const res = await apiFetch(`${API}/inventory/par-proposals/${proposalId}/accept`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function rejectParProposal(proposalId: string): Promise<ParProposalEnvelope> {
  const res = await apiFetch(`${API}/inventory/par-proposals/${proposalId}/reject`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getTrainingLessons(): Promise<TrainingLessons> {
  const res = await apiFetch(`${API}/training/lessons`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function draftTrainingLesson(position: string): Promise<TrainingLesson> {
  const res = await apiFetch(`${API}/training/lessons/draft`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position }),
  });
  return readJson(res);
}

export async function approveLesson(lessonId: string): Promise<TrainingLesson> {
  const res = await apiFetch(`${API}/training/lessons/${lessonId}/approve`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function editLesson(lessonId: string, patch: { title?: string; body?: string; position?: string }): Promise<TrainingLesson> {
  const res = await apiFetch(`${API}/training/lessons/${lessonId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return readJson(res);
}

export async function getQuiz(quizId: string): Promise<TrainingQuiz> {
  const res = await apiFetch(`${API}/training/quizzes/${quizId}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function submitQuizAttempt(quizId: string, answers: number[]): Promise<TrainingQuiz> {
  const res = await apiFetch(`${API}/training/quizzes/${quizId}/attempts`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
  return readJson(res);
}

export async function getDueReviews(): Promise<DueReviewList> {
  const res = await apiFetch(`${API}/training/reviews/due`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function startRoleplay(persona: string, dish = ""): Promise<RoleplayResponse> {
  const res = await apiFetch(`${API}/training/roleplay`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona, dish }),
  });
  return readJson(res);
}

export async function replyRoleplay(sessionId: string, text: string): Promise<RoleplayResponse> {
  const res = await apiFetch(`${API}/training/roleplay/${sessionId}/reply`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return readJson(res);
}

export async function scoreRoleplay(sessionId: string): Promise<RoleplayResponse> {
  const res = await apiFetch(`${API}/training/roleplay/${sessionId}/score`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getTeam(): Promise<TeamRoster> {
  const res = await apiFetch(`${API}/team`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getTeamProgress(): Promise<TeamProgress> {
  const res = await apiFetch(`${API}/team/progress`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function inviteTeamMember(body: { email: string; role: string; position: string | null }): Promise<TeamInvite> {
  const res = await apiFetch(`${API}/team/invites`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function revokeTeamInvite(inviteId: string): Promise<TeamInvite> {
  const res = await apiFetch(`${API}/team/invites/${inviteId}/revoke`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function updateTeamMember(userId: string, body: { role: string; position: string | null }): Promise<TeamMember> {
  const res = await apiFetch(`${API}/team/members/${userId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function removeTeamMember(userId: string): Promise<RemovedMember> {
  const res = await apiFetch(`${API}/team/members/${userId}`, { method: "DELETE", credentials: "same-origin" });
  return readJson(res);
}

export async function getTeamCertificates(): Promise<CertificateList> {
  const res = await apiFetch(`${API}/team/certificates`, { cache: "no-store", credentials: "same-origin" });
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
  const res = await apiFetch(`${API}/team/certificates`, { method: "POST", credentials: "same-origin", body });
  const payload = await readJson<{ certificate: CertificateRecord }>(res);
  return payload.certificate;
}

export async function deleteCertificate(certificateId: string): Promise<DeletedFlag> {
  const res = await apiFetch(`${API}/team/certificates/${certificateId}`, { method: "DELETE", credentials: "same-origin" });
  return readJson(res);
}

export async function getTonight(): Promise<TonightBoard> {
  const res = await apiFetch(`${API}/tonight`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getTonightBriefing(serviceDate?: string): Promise<TonightEnvelope> {
  const params = serviceDate ? `?service_date=${encodeURIComponent(serviceDate)}` : "";
  const path = `${API}/tonight/briefing${params}`;
  try {
    const res = await apiFetch(path, { cache: "no-store", credentials: "same-origin" });
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
    const res = await apiFetch(path, { cache: "no-store", credentials: "same-origin" });
    if (res.ok) return res.json();
  } catch {
    // Offline lookup uses the pack captured on the last visit.
  }
  const cached = await readCachedJson<LookupPack>(path);
  if (cached) return cached;
  throw new Error("The floor list is not on this phone yet.");
}

export async function acknowledgeBriefing(id: string, secondsToAck: number): Promise<TonightBriefing> {
  const res = await apiFetch(`${API}/tonight/briefing/${id}/ack`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seconds_to_ack: secondsToAck }),
  });
  return readJson(res);
}

export async function getBriefingReport(start: string, end: string): Promise<BriefingReport> {
  const params = new URLSearchParams({ start, end });
  const res = await apiFetch(`${API}/tonight/briefing/report?${params}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function lookupFloor(query: string): Promise<LookupResult> {
  const res = await apiFetch(`${API}/lookup?q=${encodeURIComponent(query)}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getStandards(): Promise<StandardList> {
  const res = await apiFetch(`${API}/training/standards`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function saveStandard(standard: { slug: string; title: string; body: string; topic?: string }): Promise<ServiceStandard> {
  const res = await apiFetch(`${API}/training/standards`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(standard),
  });
  return readJson(res);
}

export async function resetStandard(slug: string): Promise<ServiceStandard> {
  const res = await apiFetch(`${API}/training/standards/${slug}/reset`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getDemoPersonas(): Promise<DemoPersonaList | null> {
  const res = await apiFetch(`${API}/auth/demo-personas`, { cache: "no-store", credentials: "same-origin" });
  if (!res.ok) return null;
  return res.json();
}

export async function setDemoPersona(slug: string): Promise<void> {
  const res = await apiFetch(`${API}/auth/demo-persona`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug }),
  });
  if (!res.ok) throw new Error("The demo persona could not be changed.");
}

export async function listTastingSessions(): Promise<TastingSessionList> {
  const res = await apiFetch(`${API}/tastings`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createTastingSession(body: {
  supplier_id?: string;
  supplier_name?: string;
  title?: string;
  starts_at?: string;
  ends_at?: string;
  location?: string;
  notes?: string;
}): Promise<TastingCreateResult> {
  const res = await apiFetch(`${API}/tastings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function getTastingSession(sessionId: string): Promise<TastingSessionDetail> {
  const res = await apiFetch(`${API}/tastings/${sessionId}`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function addSample(sessionId: string): Promise<SampleEnvelope> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/samples`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({}),
  });
  return readJson(res);
}

export async function updateSample(
  sessionId: string,
  sampleId: string,
  body: { product_id?: string | null; note?: string; quoted_price_cents?: number | null; currency?: string | null },
): Promise<SampleEnvelope> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/samples/${sampleId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function scoreSample(
  sessionId: string,
  sampleId: string,
  score: number | null,
  note?: string,
): Promise<SampleEnvelope> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/samples/${sampleId}/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ score, note }),
  });
  return readJson(res);
}

export async function setSampleDecision(
  sessionId: string,
  sampleId: string,
  decision: "undecided" | "buy" | "list" | "pass",
  reason?: string,
): Promise<SampleEnvelope> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/samples/${sampleId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ decision, reason: reason ?? "" }),
  });
  return readJson(res);
}

export async function listSourcingBriefs(): Promise<SourcingBriefList> {
  const res = await apiFetch(`${API}/sourcing/briefs`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function buildSourcingBrief(): Promise<SourcingBriefEnvelope> {
  const res = await apiFetch(`${API}/sourcing/briefs`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getTastingHistory(): Promise<TastingHistory> {
  const res = await apiFetch(`${API}/sourcing/history`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getRepFollowup(sessionId: string): Promise<RepFollowupEnvelope> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/follow-up`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getTastingInvite(sessionId: string): Promise<InviteDesk> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/invite`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function proposeTastingInvite(
  sessionId: string,
  body: { slots: InviteSlot[]; staff_user_ids: string[] },
): Promise<InviteDesk> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function decideTastingInvite(
  sessionId: string,
  decision: "approve" | "reject",
  comment: string,
  slotIndex?: number,
): Promise<InviteDesk> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/invite/${decision}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment, slot_index: slotIndex ?? null }),
  });
  return readJson(res);
}

export async function draftRepFollowup(sessionId: string): Promise<RepFollowupDraft> {
  const res = await apiFetch(`${API}/tastings/${sessionId}/follow-up`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function scanSampleLabel(sessionId: string, sampleId: string, file: File): Promise<SampleEnvelope> {
  const body = new FormData();
  body.set("file", file);
  const res = await apiFetch(`${API}/tastings/${sessionId}/samples/${sampleId}/label`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getProducts(): Promise<ProductList> {
  const res = await apiFetch(`${API}/products`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getLists(): Promise<ListIndex> {
  const res = await apiFetch(`${API}/lists`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res.json();
}

async function waitForJob<T>(jobId: string): Promise<T> {
  let delay = 200;
  for (let attempt = 0; attempt < 25; attempt += 1) {
    const res = await apiFetch(`${API}/jobs/${jobId}`, { credentials: "same-origin", cache: "no-store" });
    const job = await readJson<{ status: string; last_error: string; result: T }>(res);
    if (job.status === "succeeded") return job.result;
    if (job.status === "failed" || job.status === "dead") {
      throw new ApiError(502, job.last_error || "The job failed.");
    }
    await new Promise((resolve) => setTimeout(resolve, delay));
    delay = Math.min(delay * 2, 2000);
  }
  throw new ApiError(504, "The job is still running.");
}

async function unwrapJob<T>(body: T): Promise<T> {
  if (body === null || typeof body !== "object") return body;
  const row = body as T & { job_status?: string; job_id?: string };
  if (row.job_status !== "queued" && row.job_status !== "running") return body;
  if (!row.job_id) throw new ApiError(502, "The job failed.");
  return waitForJob<T>(row.job_id);
}

export async function getTastingNotes(productId: string): Promise<TastingNoteList> {
  const res = await apiFetch(`${API}/products/${productId}/notes`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getServiceCards(productId: string): Promise<ServiceCardList> {
  const res = await apiFetch(`${API}/products/${productId}/service-cards`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function draftTastingNote(productId: string, techSheet: string, file: File | null): Promise<TastingDraft> {
  const body = new FormData();
  body.set("tech_sheet", techSheet);
  if (file) body.set("file", file);
  const res = await apiFetch(`${API}/products/${productId}/notes/draft`, {
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
  const res = await apiFetch(`${API}/products/${productId}/notes/${noteId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function approveTastingNote(productId: string, noteId: string): Promise<TastingNote> {
  const res = await apiFetch(`${API}/products/${productId}/notes/${noteId}/approve`, {
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
  const res = await apiFetch(`${API}/products/${productId}/service-cards/${cardId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function approveServiceCard(productId: string, cardId: string): Promise<ServiceCardRecord> {
  const res = await apiFetch(`${API}/products/${productId}/service-cards/${cardId}/approve`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function importList(file: File, confirm: boolean): Promise<ListImportResult> {
  const body = new FormData();
  body.set("file", file);
  body.set("confirm", confirm ? "true" : "false");
  const res = await apiFetch(`${API}/lists/import`, { method: "POST", body, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return unwrapJob(await res.json());
}

export async function getSampleMenu() {
  const res = await apiFetch(`${API}/fixtures/sample-menu`, { cache: "no-store" });
  return res.json();
}

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
  const res = await apiFetch(`${API}/settings/llm`, { cache: "no-store", credentials: "same-origin" });
  return readSettings(res);
}

export async function saveLlmSettings(body: {
  provider: string;
  model: string;
  api_key: string;
}): Promise<LlmSettings> {
  const res = await apiFetch(`${API}/settings/llm`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readSettings(res);
}

export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await apiFetch(`${API}/auth/config`, { cache: "no-store" });
  if (!res.ok) throw new Error("auth config failed");
  const data = (await res.json()) as { configured?: boolean };
  return { configured: data.configured === true };
}

export async function getAccount(): Promise<Account | null> {
  try {
    const res = await apiFetch(`${API}/auth/me`, { cache: "no-store", credentials: "same-origin" });
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
    const res = await apiFetch(`${API}/auth/logout`, { method: "POST", credentials: "same-origin" });
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

export async function getAuditEvents(filters?: {
  entity_type?: string;
  action?: string;
}): Promise<AuditEventList> {
  const params = new URLSearchParams();
  if (filters?.entity_type) params.set("entity_type", filters.entity_type);
  if (filters?.action) params.set("action", filters.action);
  const query = params.toString();
  const res = await apiFetch(`${API}/compliance/audit-events${query ? `?${query}` : ""}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function listDocuments(): Promise<DocumentList> {
  const res = await apiFetch(`${API}/compliance/documents`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function uploadDocument(input: {
  file: File;
  doc_type: string;
  linked_entity_type?: string;
  linked_entity_id?: string;
}): Promise<DocumentEnvelope> {
  const body = new FormData();
  body.set("file", input.file);
  body.set("doc_type", input.doc_type);
  if (input.linked_entity_type) body.set("linked_entity_type", input.linked_entity_type);
  if (input.linked_entity_id) body.set("linked_entity_id", input.linked_entity_id);
  const res = await apiFetch(`${API}/compliance/documents`, { method: "POST", body, credentials: "same-origin" });
  return readJson(res);
}

export async function getRetention(): Promise<RetentionPolicy> {
  const res = await apiFetch(`${API}/compliance/retention`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function updateRetention(years: number): Promise<RetentionPolicy> {
  const res = await apiFetch(`${API}/compliance/retention`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_retention_years: years }),
  });
  return readJson(res);
}

export async function listProcurementSuppliers(): Promise<SupplierList> {
  const res = await apiFetch(`${API}/procurement/suppliers`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createProcurementSupplier(body: {
  name: string;
  default_case_size: number;
  order_minimum_cents: number;
  delivery_days: string[];
  lead_time_days: number;
  payment_terms?: string;
}): Promise<SupplierEnvelope> {
  const res = await apiFetch(`${API}/procurement/suppliers`, {
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
): Promise<ContactEnvelope> {
  const res = await apiFetch(`${API}/procurement/suppliers/${supplierId}/contacts`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function getSupplierDesk(supplierId: string): Promise<SupplierDeskPayload> {
  const res = await apiFetch(`${API}/procurement/suppliers/${supplierId}/desk`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function saveSupplierProfile(
  supplierId: string,
  body: {
    rep_name: string;
    rep_email: string;
    rep_phone: string;
    delivery_days: string[];
    order_minimum_cents: number;
    order_minimum_currency: string;
    payment_terms: string;
    notes: string;
  },
): Promise<ProfileEnvelope> {
  const res = await apiFetch(`${API}/procurement/suppliers/${supplierId}/profile`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function createAllocation(
  supplierId: string,
  body: { product_id: string; quantity: number; period_label: string; period_start?: string; period_end?: string },
): Promise<AllocationEnvelope> {
  const res = await apiFetch(`${API}/procurement/suppliers/${supplierId}/allocations`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function deleteAllocation(allocationId: string): Promise<DeletedId> {
  const res = await apiFetch(`${API}/procurement/allocations/${allocationId}`, {
    method: "DELETE",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function uploadPriceSheet(supplierId: string, file: File): Promise<PriceSheetEnvelope> {
  const body = new FormData();
  body.set("supplier_id", supplierId);
  body.set("file", file);
  const res = await apiFetch(`${API}/procurement/price-sheets`, {
    method: "POST",
    credentials: "same-origin",
    body,
  });
  return unwrapJob(await readJson(res));
}

export async function applyPriceSheet(sheetId: string): Promise<PriceSheetApplied> {
  const res = await apiFetch(`${API}/procurement/price-sheets/${sheetId}/apply`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function rejectPriceSheet(sheetId: string): Promise<PriceSheetApplied> {
  const res = await apiFetch(`${API}/procurement/price-sheets/${sheetId}/reject`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function getPriceHistory(productId: string): Promise<PriceHistory> {
  const res = await apiFetch(`${API}/procurement/products/${productId}/price-history`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function listLifecycleOrders(): Promise<PurchaseOrderList> {
  const res = await apiFetch(`${API}/procurement/orders`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createLifecycleOrder(body: {
  supplier_id: string;
  notes?: string;
  lines: { sku: string; product_name: string; bottles: number; unit_cost_cents: number }[];
}): Promise<PurchaseOrderRow> {
  const res = await apiFetch(`${API}/procurement/orders`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function draftLifecycleOrders(): Promise<PurchaseOrderList> {
  const res = await apiFetch(`${API}/procurement/orders/draft-from-reorder`, {
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
  const res = await apiFetch(`${API}/procurement/orders/${poId}/${decision}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  return readJson(res);
}

export async function sendPurchaseOrder(poId: string): Promise<PurchaseOrderRow> {
  const res = await apiFetch(`${API}/procurement/orders/${poId}/send`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function closePurchaseOrder(poId: string): Promise<PurchaseOrderRow> {
  const res = await apiFetch(`${API}/procurement/orders/${poId}/close`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function cancelPurchaseOrder(poId: string): Promise<PurchaseOrderRow> {
  const res = await apiFetch(`${API}/procurement/orders/${poId}/cancel`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

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
  const res = await apiFetch(`${API}/procurement/orders/${poId}/invoices`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  return unwrapJob(await readJson(res));
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
  const res = await apiFetch(`${API}/procurement/orders/${poId}/receipts`, {
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
  const res = await apiFetch(`${API}/procurement/receipts/${receiptId}/accept`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res);
}

export async function deleteLlmSettings(): Promise<LlmSettings> {
  const res = await apiFetch(`${API}/settings/llm`, { method: "DELETE", credentials: "same-origin" });
  return readSettings(res);
}

export async function getSensors(): Promise<SensorList> {
  const res = await apiFetch(`${API}/sensors`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createSensor(body: {
  name: string;
  zone_id: string;
  metric: string;
  external_id: string;
}): Promise<SensorRecord> {
  const res = await apiFetch(`${API}/sensors`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function previewSensorCsv(file: File): Promise<SensorImport> {
  const body = new FormData();
  body.set("file", file);
  body.set("filename", file.name);
  const res = await apiFetch(`${API}/sensors/imports`, { method: "POST", credentials: "same-origin", body });
  return unwrapJob(await readJson(res));
}

export async function applySensorImport(importId: string): Promise<SensorImport> {
  const res = await apiFetch(`${API}/sensors/imports/${importId}/apply`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function rejectSensorImport(importId: string): Promise<SensorImport> {
  const res = await apiFetch(`${API}/sensors/imports/${importId}/reject`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function decideReminder(body: {
  source_type: string;
  source_id: string;
  action: "acknowledge" | "snooze";
  snooze_days?: number;
}): Promise<ReminderDecision> {
  const res = await apiFetch(`${API}/reminders/decide`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function listStorageZones(): Promise<StorageZoneList> {
  const res = await apiFetch(`${API}/inventory/storage-zones`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function recordZoneReading(
  zoneId: string,
  tempC: number,
  humidityPct: number,
  notes?: string,
): Promise<ZoneReadingResult> {
  const res = await apiFetch(`${API}/inventory/storage-zones/${zoneId}/readings`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ temp_c: tempC, humidity_pct: humidityPct, notes: notes || null }),
  });
  return readJson(res);
}

export async function acknowledgeExcursion(excursionId: string, resolutionNote?: string): Promise<ZoneExcursionEnvelope> {
  const res = await apiFetch(`${API}/inventory/excursions/${excursionId}/acknowledge`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolution_note: resolutionNote || null }),
  });
  return readJson(res);
}

export async function previewAuditPack(startDate: string, endDate: string): Promise<AuditPackPreview> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  const res = await apiFetch(`${API}/compliance/audit-pack/preview?${params}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function curateList(body: {
  budget: number;
  target_margin: number;
  target_beverage_cost_pct?: number | null;
  concept?: string;
  price_tier?: string;
  name?: string;
}): Promise<BeverageListDetail> {
  const res = await apiFetch(`${API}/lists/curate`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function addListItem(listId: string, skuId: string, section = ""): Promise<BeverageListDetail> {
  const res = await apiFetch(`${API}/lists/${listId}/items`, {
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
  const res = await apiFetch(`${API}/lists/${listId}/items/${itemId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return readJson(res);
}

export async function deleteListItem(listId: string, itemId: string): Promise<BeverageListDetail> {
  const res = await apiFetch(`${API}/lists/${listId}/items/${itemId}`, {
    method: "DELETE",
    credentials: "same-origin",
  });
  return readJson(res);
}

export async function listVersions(listId: string): Promise<ListVersionIndex> {
  const res = await apiFetch(`${API}/lists/${listId}/versions`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function createListVersion(listId: string): Promise<ListVersionRecord> {
  const res = await apiFetch(`${API}/lists/${listId}/versions`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function submitListVersion(versionId: string): Promise<ListVersionRecord> {
  const res = await apiFetch(`${API}/lists/versions/${versionId}/submit`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function decideListVersion(
  versionId: string,
  decision: "approve" | "reject",
  comment = "",
): Promise<ListVersionRecord> {
  const res = await apiFetch(`${API}/lists/versions/${versionId}/${decision}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  return readJson(res);
}

export async function revokePublicList(versionId: string): Promise<ListVersionRecord> {
  const res = await apiFetch(`${API}/lists/versions/${versionId}/revoke-public`, {
    method: "POST",
    credentials: "same-origin",
  });
  return readJson(res);
}

export function listQrPath(versionId: string) {
  return `${API}/lists/versions/${versionId}/qr.png`;
}

export async function getPublicList(token: string): Promise<PublicList> {
  const res = await apiFetch(`${API}/public/lists/${encodeURIComponent(token)}`, { cache: "no-store" });
  return readJson(res);
}

export async function getPosStatus(): Promise<PosStatus> {
  const res = await apiFetch(`${API}/pos/status`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getPosCatalog(): Promise<PosCatalog> {
  const res = await apiFetch(`${API}/pos/catalog`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getPosMappings(): Promise<PosMappingList> {
  const res = await apiFetch(`${API}/pos/mappings`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getPosRuns(): Promise<PosRunList> {
  const res = await apiFetch(`${API}/pos/runs`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function getPosGaps(): Promise<PosGapList> {
  const res = await apiFetch(`${API}/pos/gaps`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function connectDemoPos(): Promise<PosStatus> {
  const res = await apiFetch(`${API}/pos/connect/demo`, { method: "POST", credentials: "same-origin" });
  return readJson(res);
}

export async function connectSquarePos(accessToken: string, locationId = ""): Promise<PosStatus> {
  const res = await apiFetch(`${API}/pos/connect/square`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken, location_id: locationId }),
  });
  return readJson(res);
}

export async function choosePosLocation(locationId: string): Promise<PosStatus> {
  const res = await apiFetch(`${API}/pos/location`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ location_id: locationId }),
  });
  return readJson(res);
}

export async function savePosMapping(body: {
  variation_id: string;
  item_id: string;
  sku: string;
  pour_ml: number | null;
  units_per_sale: string;
}): Promise<PosMappingEnvelope> {
  const res = await apiFetch(`${API}/pos/mappings`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function syncPos(): Promise<PosSyncResult> {
  const res = await apiFetch(`${API}/pos/sync`, { method: "POST", credentials: "same-origin" });
  return unwrapJob(await readJson(res));
}

export async function getUsage(): Promise<UsageReport> {
  const res = await apiFetch(`${API}/usage`, { cache: "no-store", credentials: "same-origin" });
  return readJson(res);
}

export async function saveUsageLimits(body: {
  monthly_spend_cap_cents: number | null;
  requests_per_minute: number | null;
}): Promise<UsageReport> {
  const res = await apiFetch(`${API}/usage/limits`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function getAuditQuery(kind: string, offset = 0): Promise<AuditorQuery> {
  const path: Record<string, string> = {
    stock: "/compliance/queries/stock",
    conditions: "/compliance/queries/conditions",
    compliance: "/compliance/queries/compliance",
    pos: "/compliance/queries/pos",
    lists: "/compliance/queries/lists",
    purchases: "/compliance/queries/purchases",
    events: "/compliance/queries/events",
  };
  const res = await apiFetch(`${API}${path[kind] || path.stock}?limit=25&offset=${offset}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  return readJson(res);
}

export function auditPackExportPath(startDate: string, endDate: string, format: "zip" | "journal_csv" | "summary_pdf" | "summary_csv") {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate, format });
  return `${API}/compliance/audit-pack/export?${params}`;
}
