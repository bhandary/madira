/**
 * Generated from the FastAPI OpenAPI schema (`app.openapi()`). Do not edit.
 * Regenerate with `make types`.
 */

export type AcceptBody = {
  acknowledge_discrepancies?: boolean;
  notes?: string | null;
};

export type Account = {
  name: string;
  email: string;
  picture: string;
};

export type AccountEnvelope = {
  user: Account | null;
};

export type AckBody = {
  seconds_to_ack: number;
};

export type AcknowledgeBody = {
  resolution_note?: string | null;
};

export type AffectedSku = {
  sku: string;
  product_name: string;
  bin_code: string;
  on_hand: number;
};

export type AguiMessages = {
  messages: Array<Record<string, unknown>>;
};

export type AllocationBody = {
  product_id?: string | null;
  quantity?: number | null;
  period_label?: string | null;
  period_start?: string | null;
  period_end?: string | null;
};

export type AllocationEnvelope = {
  allocation: AllocationRecord;
};

export type AllocationRecord = {
  id: string;
  supplier_id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  period_label: string;
  period_start: string | null;
  period_end: string | null;
};

export type AttemptBody = {
  answers: number[] | string;
};

export type AuditChain = {
  valid: boolean;
  checked_count: number;
  head_hash: string | null;
  broken_event_id: string | null;
  reason: string | null;
};

export type AuditEventList = {
  events: AuditEventRow[];
  chain: AuditChain;
};

export type AuditEventRow = {
  id: string;
  seq: number;
  actor_email: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  prev_hash: string;
  event_hash: string;
  created_at: string;
  summary: string;
};

export type AuditPackChain = {
  valid: boolean;
  checked: number;
  head_hash: string | null;
};

export type AuditPackGap = {
  purchase_order_id: string;
  po_number: string;
  supplier: string;
  status: string;
  reason: string;
};

export type AuditPackInvoice = {
  invoice_number: string;
  total_cents: number;
  status: string;
};

export type AuditPackPreview = {
  venue: AuditVenue;
  start_date: string;
  end_date: string;
  purchases_by_supplier: AuditPackPurchase[];
  invoice_register: AuditPackInvoice[];
  missing_invoice_gaps: AuditPackGap[];
  inventory_valuation: AuditValuation;
  variance_and_shrinkage: AuditVariance;
  comp_breakage_waste: AuditWaste;
  retention: AuditRetention;
  chain: AuditPackChain;
};

export type AuditPackPurchase = {
  supplier: string;
  po_count: number;
  invoice_count: number;
  total_invoiced_cents: number;
  total_received_value_cents: number;
};

export type AuditRetention = {
  document_retention_years: number;
  retain_until: string;
};

export type AuditValuation = {
  start_bottles: number;
  start_value_cents: number;
  end_bottles: number;
  end_value_cents: number;
};

export type AuditVariance = {
  quantity_delta: number;
  cost_impact_cents: number;
  count_sessions: unknown[];
};

export type AuditVenue = {
  id: string;
  name: string;
};

export type AuditWaste = {
  cost_impact_cents: number;
  movements: unknown[];
};

export type AuditorColumn = {
  key: string;
  label: string;
  type: "text" | "number" | "money" | "date";
};

export type AuditorLink = {
  label: string;
  href: string;
};

export type AuditorPage = {
  limit: number;
  offset: number;
  total: number;
};

export type AuditorQuery = {
  audit_table: AuditorTable;
};

export type AuditorRow = {
  id: string;
  cells: Record<string, string | number>;
  links: AuditorLink[];
};

export type AuditorTable = {
  title: string;
  columns: AuditorColumn[];
  rows: AuditorRow[];
  totals: Record<string, string | number>;
  page: AuditorPage;
};

export type AuthConfig = {
  configured: boolean;
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
  health: ListHealth;
  candidates: ListCandidate[];
  bottles: number;
  capacity_bottles: number | null;
};

export type BinBody = {
  location_id: string;
  code: string;
  label?: string;
};

export type BinEnvelope = {
  bin: CellarBin;
};

export type BinLabel = {
  bin_id: string;
  code: string;
  label: string;
  qr_payload: string;
  svg: string;
};

export type BinList = {
  bins: CellarBin[];
};

export type Body_create_draft_products__product_id__notes_draft_post = {
  tech_sheet?: string;
  file?: string | null;
};

export type Body_documents_upload_compliance_documents_post = {
  file: string;
  doc_type: string;
  linked_entity_type?: string;
  linked_entity_id?: string;
};

export type Body_import_list_lists_import_post = {
  file: string;
  confirm?: string;
  name?: string;
};

export type Body_procurement_invoice_upload_procurement_orders__po_id__invoices_post = {
  file: string;
  invoice_number: string;
  invoice_date: string;
  tax_cents?: number;
  lines_json?: string;
};

export type Body_sample_label_tastings__session_id__samples__sample_id__label_post = {
  file: string;
};

export type Body_samples_label_tastings__session_id__samples_label_post = {
  file: string;
};

export type Body_team_certificate_create_team_certificates_post = {
  user_id: string;
  kind: string;
  label?: string;
  issued_on: string;
  expires_on: string;
  file?: string | null;
};

export type Body_team_certificate_document_team_certificates__certificate_id__document_post = {
  file: string;
};

export type Body_upload_csv_sensors_imports_post = {
  file: string;
  filename?: string;
};

export type Body_upload_menu_menus_ingest_post = {
  file?: string | null;
  text?: string;
  url?: string;
  menu_id?: string;
};

export type Body_upload_menu_menus_upload_post = {
  file?: string | null;
  text?: string;
  url?: string;
  menu_id?: string;
};

export type Body_upload_price_sheet_procurement_price_sheets_post = {
  supplier_id: string;
  file: string;
};

export type BriefingAckStat = {
  acked: number;
  published: number;
  rate_bp: number | null;
  label: string;
};

export type BriefingCard = {
  kind: string;
  title: string;
  body: string;
  items: BriefingItem[];
};

export type BriefingItem = {
  title: string;
  detail: string;
};

export type BriefingReport = {
  start: string;
  end: string;
  days: BriefingReportDay[];
};

export type BriefingReportDay = {
  service_date: string;
  briefing_id: string | null;
  status: string | null;
  acknowledged_count: number;
  user_count: number;
  users: BriefingReportUser[];
};

export type BriefingReportUser = {
  user_id: string;
  name: string;
  acknowledged: boolean;
  seconds_to_ack: number | null;
};

export type CardEdit = {
  serving_temperature?: string | null;
  glassware?: string | null;
  decanting?: string | null;
  pour_size?: string | null;
};

export type CatalogChoice = {
  product_id: string;
  sku_id: string;
  name: string;
  producer: string;
  barcode: string;
};

export type CatalogProduct = {
  id: string;
  category: string;
  producer: string;
  name: string;
  region: string;
  country: string;
  style: string;
  grape: string;
  body: string;
  acidity: string;
  tannin: string;
  sweetness: string;
  oak: string;
  intensity: string;
  aroma_families: string[];
  variants: CatalogVariant[];
};

export type CatalogSku = {
  id: string;
  product_id: string;
  variant_id: string;
  barcode: string;
  bin_label: string;
  par: number;
  cost: number;
  currency: string;
  vintage: string;
  bottle_size: string;
  category: string;
  producer: string;
  name: string;
  region: string;
  country: string;
  style: string;
  grape: string;
  body: string;
  acidity: string;
  tannin: string;
  sweetness: string;
  oak: string;
  intensity: string;
  aroma_families: string[];
};

export type CatalogVariant = {
  id: string;
  vintage: string;
  bottle_size: string;
  sku_id: string;
};

export type CellarBin = {
  id: string;
  location_id: string;
  location_name: string;
  code: string;
  label: string;
  qr_payload: string;
};

export type CellarBoard = {
  items: StockItem[];
  locations: CellarLocation[];
};

export type CellarLocation = {
  id: string;
  name: string;
  kind: string;
  notes: string;
};

export type CertificateEnvelope = {
  certificate: CertificateRecord;
};

export type CertificateGap = {
  id: string;
  user_id: string;
  name: string;
  kind: string;
  label: string;
  issued_on: string;
  expires_on: string;
  days_left: number;
  status_label: string;
};

export type CertificateList = {
  certificates: CertificateRecord[];
};

export type CertificatePatch = {
  kind?: string | null;
  label?: string | null;
  issued_on?: string | null;
  expires_on?: string | null;
};

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

export type ComplianceGaps = {
  missing_invoice_gaps: unknown[];
  open_excursions: unknown[];
  certificate_gaps: unknown[];
  pos_gaps: unknown[];
  reminders: unknown[];
  chain: AuditPackChain;
};

export type ContactBody = {
  name: string;
  role?: string | null;
  email: string;
  phone?: string | null;
  is_primary?: boolean;
};

export type ContactEnvelope = {
  contact: SupplierContactRow;
  supplier: SupplierRow;
};

export type CountConflict = {
  sku: string;
  readings: CountReading[];
  resolved: boolean;
  resolved_quantity: number | null;
};

export type CountLineRecord = {
  id: string;
  sku: string;
  name: string;
  counted_quantity: number;
  expected_quantity: number | null;
  device_id: string;
  bin_code: string;
  counted_at: string | null;
};

export type CountMovement = {
  id: string;
  sku: string;
  quantity: number;
  movement_type: string;
};

export type CountReading = {
  device_id: string;
  counted_quantity: number;
  counted_at: string | null;
};

export type CountReport = {
  session: CountSessionRecord;
  lines: CountLineRecord[];
  variance_lines: VarianceLine[];
  conflicts: CountConflict[];
  movements?: CountMovement[];
};

export type CountSessionList = {
  sessions: CountSessionRecord[];
};

export type CountSessionRecord = {
  id: string;
  location_id: string;
  location_name: string;
  status: string;
  notes: string;
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

export type DecideBody = {
  source_type: string;
  source_id: string;
  action: string;
  snooze_days?: number;
};

export type DeletedFlag = {
  deleted: boolean;
  id: string;
};

export type DeletedId = {
  deleted: string;
};

export type DeliveryDue = {
  po_number: string;
  supplier: string;
  expected_delivery_date: string | null;
  status: string;
};

export type DemoPersona = {
  slug: string;
  name: string;
  role: string;
  position: string | null;
  email: string;
};

export type DemoPersonaList = {
  active: string;
  personas: DemoPersona[];
};

export type DiscrepancyLine = {
  sku: string;
  flags: string[];
  cost_delta_cents: number;
};

export type DiscrepancySummary = {
  has_discrepancies: boolean;
  counts: Record<string, number>;
  cost_delta_cents: number;
  lines: DiscrepancyLine[];
};

export type DishFieldEdit = {
  field: string;
  value?: unknown;
};

export type DocumentEnvelope = {
  document: VaultDocument;
};

export type DocumentList = {
  documents: VaultDocument[];
};

export type DraftBody = {
  position: string;
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

export type DueReviewList = {
  reviews: DueReview[];
};

export type EightySixResult = {
  id: string;
  sku: string;
  name: string;
  eighty_sixed_at: string | null;
  eighty_sixed: boolean;
};

export type GenerateBody = {
  lead_time_days?: number;
  safety_days?: number;
  proposed_by?: string;
};

export type HTTPValidationError = {
  detail?: ValidationError[];
};

export type HealthFlag = {
  code: string;
  message: string;
  dish_id: string | null;
  item_id: string | null;
  sku_id: string | null;
  section: string;
};

export type HealthPayload = {
  status: string;
  app: string;
  demo_mode: boolean;
  llm_provider: string;
  llm_model: string;
  llm_source: string;
  label: string;
  database: string;
};

export type InviteApproval = {
  id?: string;
  decision?: string;
  required_role?: string;
  comment?: string | null;
  decided_at?: string | null;
};

export type InviteAttendee = {
  kind: string;
  name: string;
  email: string;
  user_id?: string | null;
};

export type InviteBody = {
  email: string;
  role: string;
  position?: string | null;
};

export type InviteDecisionBody = {
  comment?: string;
  slot_index?: number | null;
};

export type InviteDesk = {
  suggestions: InviteSlot[];
  staff: InviteStaff[];
  rep: InviteRep;
  can_decide: boolean;
  invite: TastingInvite | null;
};

export type InviteFacts = {
  source: string;
  gaps: InviteGap[];
  samples: InviteSampleRef[];
};

export type InviteGap = {
  category: string;
  style: string;
  price_band: string;
  quantity_hint: number;
  dishes: InviteGapDish[];
};

export type InviteGapDish = {
  name: string;
};

export type InviteProposeBody = {
  slots?: InviteSlotBody[] | null;
  staff_user_ids?: string[] | null;
};

export type InviteRep = {
  supplier: string;
  name: string;
  email: string;
};

export type InviteSampleRef = {
  sample_id: string;
  name: string;
};

export type InviteSlot = {
  position?: number;
  starts_at: string;
  ends_at: string;
  source?: string;
  chosen?: boolean;
};

export type InviteSlotBody = {
  starts_at: string;
  ends_at?: string;
  source?: string;
};

export type InviteStaff = {
  id: string;
  name: string;
  email: string;
  role: string;
};

export type InvoiceLine = {
  sku: string;
  product_name?: string;
  quantity: number;
  unit_cost_cents: number;
  vintage?: string | null;
  po_line_id?: string | null;
};

export type InvoiceList = {
  invoices: InvoiceRecord[];
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

export type ItemBody = {
  sku_id: string;
  section?: string;
};

export type ItemPatch = {
  reprice?: boolean;
  pour_price?: number | null;
  bottle_price?: number | null;
  position?: number | null;
  section?: string | null;
};

export type LessonBottle = {
  sku_id: string;
  name: string;
};

export type LessonPatch = {
  title?: string | null;
  body?: string | null;
  position?: string | null;
};

export type LessonStandard = {
  id: string;
  slug: string;
  title: string;
};

export type LicenseBody = {
  label: string;
  expires_on: string;
  rule_code?: string;
  document_id?: string | null;
};

export type LicenseRecorded = {
  id: string;
  label: string;
  expires_on: string;
  rule_code?: string;
  document_id?: string | null;
};

export type LimitsBody = {
  monthly_spend_cap_cents?: number | null;
  requests_per_minute?: number | null;
};

export type LineBody = {
  sku: string;
  product_name?: string;
  sku_id?: string | null;
  case_size?: number | null;
  cases_ordered?: number | null;
  bottles?: number | null;
  quantity_ordered?: string | null;
  unit_cost_cents?: number | null;
  vintage?: string | null;
  notes?: string | null;
};

export type ListBody = {
  budget?: number;
  target_margin?: number;
  target_beverage_cost_pct?: number | null;
  concept?: string;
  price_tier?: string;
  name?: string;
  menu_id?: string | null;
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

export type ListCoverage = {
  filled: number;
  open: number;
  cells: CoverageCell[];
  suggestions: CoverageCell[];
  list_id: string;
};

export type ListDiff = {
  added: ListDiffRow[];
  removed: ListDiffRow[];
  repriced: ListDiffRow[];
  moved: ListDiffRow[];
};

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

export type ListHealth = {
  list_id: string;
  flags: HealthFlag[];
};

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
  list?: ListImportSaved | null;
};

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

export type ListImportSaved = {
  id: string;
  name: string;
  currency: string;
  item_count: number;
  source_filename: string;
  items: ListImportItem[];
};

export type ListIndex = {
  lists: BeverageListDetail[];
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

export type ListVersionApproval = {
  id?: string;
  decision?: string;
  required_role?: string;
  comment?: string | null;
  decided_at?: string | null;
};

export type ListVersionIndex = {
  list_id: string;
  can_submit: boolean;
  versions: ListVersionRecord[];
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
  approval: ListVersionApproval | null;
  diff: ListDiff;
};

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

export type LocationEnvelope = {
  location: CellarLocation;
};

export type LocationList = {
  locations: CellarLocation[];
};

export type LookupFilters = {
  text: string;
  grape: string;
  producer: string;
  region: string;
  dish: string;
  style: string;
  max_price_cents: number | null;
  body: string[];
  acidity: string[];
  tannin: string[];
  sweetness: string[];
  oak: string[];
  intensity: string[];
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

export type LookupPack = {
  service_date: string;
  items: PackItem[];
  notes: PackNote[];
  cards: PackCard[];
  dishes: PackDish[];
  pairings: PackPairing[];
};

export type LookupResult = {
  query: string;
  filters: LookupFilters;
  results: LookupHit[];
};

export type LowStockRow = {
  sku: string;
  name: string;
  on_hand: number;
  par: number;
};

export type MappingBody = {
  variation_id: string;
  item_id?: string;
  sku: string;
  pour_ml?: number | null;
  units_per_sale?: string;
};

export type MembershipBody = {
  role: string;
  position?: string | null;
};

export type MenuDetail = {
  id: string;
  name: string;
  cuisine: string;
  price_tier: string;
  raw_text: string;
  version_id: string | null;
  version_number: number | null;
  status: string;
  dishes: MenuDetailDish[];
};

export type MenuDetailDish = {
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
  description?: string;
  flavor_profile?: string;
  content_hash?: string;
  pairings?: PairingSlot[];
};

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

export type MenuIngestResult = {
  menu_id: string;
  version_id: string;
  name: string;
  status: string;
  review: MenuReview;
};

export type MenuList = {
  menus: MenuSummary[];
};

export type MenuParseDish = {
  id: string;
  name: string;
  course: string;
  description: string;
  flavor_profile: string;
  price: number;
  currency: string;
};

export type MenuParseResult = {
  menu_id: string;
  name: string;
  cuisine: string;
  price_tier: string;
  dishes: MenuParseDish[];
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

export type MenuSummary = {
  id: string;
  name: string;
  cuisine: string;
  price_tier: string;
  dish_count: number;
  status: string;
};

export type MovementBody = {
  sku: string;
  location_id: string;
  quantity: number | string;
  movement_type: string;
  bin_id?: string | null;
  unit_cost_cents?: number | null;
  source_type?: string | null;
  source_id?: string | null;
  reason?: string | null;
};

export type MovementEnvelope = {
  movement: StockMovementRow;
};

export type MovementList = {
  movements: StockMovementRow[];
};

export type NoteDraft = {
  server_hook: string;
  guest_description: string;
  technical_note: string;
  body: "light" | "medium" | "full";
  acidity: "low" | "medium" | "high";
  tannin: "none" | "low" | "medium" | "high";
  sweetness: "bone-dry" | "dry" | "off-dry" | "medium-sweet" | "sweet";
  oak: "none" | "light" | "medium" | "heavy";
  intensity: "subtle" | "medium" | "pronounced";
  aroma_families: string[];
  serving_temperature: string;
  glassware: string;
  decanting: string;
  pour_size: string;
};

export type NoteEdit = {
  server_hook?: string | null;
  guest_description?: string | null;
  technical_note?: string | null;
  body?: string | null;
  acidity?: string | null;
  tannin?: string | null;
  sweetness?: string | null;
  oak?: string | null;
  intensity?: string | null;
  aroma_families?: string[] | null;
};

export type OfferBody = {
  supplier_id?: string | null;
  product_id?: string | null;
  sku_id?: string | null;
  unit?: string | null;
  case_size?: number | null;
  price_cents?: number | null;
  currency?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
};

export type OfferEnvelope = {
  offer: OfferRecord;
};

export type OfferList = {
  offers: OfferRecord[];
};

export type OfferRecord = {
  id: string;
  supplier_id: string;
  supplier: string;
  product_id: string;
  product_name: string;
  sku_id: string | null;
  sku: string;
  unit: string;
  case_size: number;
  price_cents: number;
  price_label: string;
  currency: string;
  valid_from: string;
  valid_to: string | null;
  source: string;
  source_document_id: string | null;
  price_sheet_id: string | null;
};

export type OkResponse = {
  ok: boolean;
};

export type OrderBody = {
  supplier_id: string;
  lines: LineBody[];
  notes?: string | null;
};

export type PackCard = {
  id: string;
  product_id: string;
  glassware: string;
  serving_temperature: string;
  pour_size: string;
  decanting: string;
};

export type PackDish = {
  id: string;
  name: string;
  description: string;
  course: string;
};

export type PackItem = {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  producer: string;
  grape: string;
  region: string;
  style: string;
  category: string;
  body: string;
  acidity: string;
  tannin: string;
  sweetness: string;
  oak: string;
  intensity: string;
  on_list: boolean;
  price_cents: number;
  currency: string;
  stock: number;
  eighty_six: boolean;
};

export type PackNote = {
  id: string;
  product_id: string;
  server_hook: string;
  guest_description: string;
  body: string;
  acidity: string;
  tannin: string;
  sweetness: string;
  oak: string;
  intensity: string;
};

export type PackPairing = {
  id: string;
  sku_id: string;
  dish_id: string;
  dish: string;
  course: string;
  description: string;
  script: string;
  pinned: boolean;
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

export type PairingOption = {
  sku_id: string;
  name: string;
  producer: string;
  category: string;
  style: string;
};

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

export type PairingSwap = {
  sku_id: string;
};

export type ParProposalEnvelope = {
  proposal: ParProposalRecord;
};

export type ParProposalList = {
  proposals: ParProposalRecord[];
};

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

export type PersonaBody = {
  slug: string;
};

export type PosAlert = {
  kind: string;
  title: string;
  href?: string;
};

export type PosCatalog = {
  items: PosCatalogItem[];
};

export type PosCatalogItem = {
  item_id: string;
  variation_id: string;
  name: string;
  variation_name: string;
  sku_hint: string;
};

export type PosGapItem = {
  variation_id: string;
  item_id: string;
  name: string;
  quantity: string;
};

export type PosGapList = {
  items: PosGapItem[];
};

export type PosLocation = {
  location_id: string;
  name: string;
};

export type PosMapping = {
  id: string;
  provider: string;
  item_id: string;
  variation_id: string;
  sku_id: string;
  sku: string;
  pour_ml: number | null;
  units_per_sale: number;
};

export type PosMappingEnvelope = {
  mapping: PosMapping;
};

export type PosMappingList = {
  mappings: PosMapping[];
};

export type PosRun = {
  id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  posted: number;
  skipped: number;
  unmapped_count: number;
  error: string;
};

export type PosRunList = {
  runs: PosRun[];
};

export type PosStatus = {
  connected: boolean;
  provider: string;
  status: string;
  location_id: string;
  location_name: string;
  key_last4: string;
  masked: string;
  last_synced_at: string | null;
  watermark: string;
  demo_mode: boolean;
  locations?: PosLocation[];
};

export type PosSyncResult = {
  posted: number;
  skipped: number;
  unmapped: PosGapItem[];
};

export type PriceHistory = {
  product: PriceProduct;
  points: PricePointRecord[];
};

export type PricePointRecord = {
  date: string;
  kind: string;
  price_cents: number;
  price_label: string;
  currency: string;
  supplier_id: string;
  supplier: string;
  source: string;
  offer_id: string | null;
  invoice_id: string | null;
};

export type PriceProduct = {
  id: string;
  name: string;
  producer: string;
};

export type PriceSheetApplied = {
  price_sheet: PriceSheetRecord;
  offers: OfferRecord[];
};

export type PriceSheetEnvelope = {
  price_sheet: PriceSheetRecord;
};

export type PriceSheetLine = {
  line: number;
  name: string;
  producer: string;
  sku: string;
  unit: string;
  case_size: number;
  price_cents: number;
  price_label: string;
  currency: string;
  valid_from: string;
  valid_to: string | null;
  product_id: string | null;
  sku_id: string | null;
  product_name: string;
  status: string;
  message: string;
};

export type PriceSheetRecord = {
  id: string;
  supplier_id: string;
  supplier: string;
  document_id: string;
  status: string;
  rows: PriceSheetLine[];
  matched: number;
  unmatched: number;
  created_at: string | null;
  reviewed_at: string | null;
};

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

export type PricingRuleBody = {
  category: string;
  cost_min_cents: number;
  cost_max_cents?: number | null;
  bottle_multiple: number;
  glass_pours_per_bottle?: number;
  glass_multiple?: number;
  round_to_cents?: number;
};

export type PricingRulesBody = {
  rules: PricingRuleBody[];
};

export type PricingRulesResponse = {
  source: string;
  rules: PricingRule[];
};

export type ProductList = {
  products: CatalogProduct[];
};

export type ProfileBody = {
  rep_name?: string | null;
  rep_email?: string | null;
  rep_phone?: string | null;
  delivery_days?: string[] | null;
  order_minimum_cents?: number | null;
  order_minimum_currency?: string | null;
  payment_terms?: string | null;
  notes?: string | null;
};

export type ProfileEnvelope = {
  supplier: SupplierProfile;
};

export type PublicList = {
  venue_name: string;
  published_at: string | null;
  list: PublicListBody;
};

export type PublicListBody = {
  list_name: string;
  number: number;
  currency: string;
  sections: PublicListSection[];
};

export type PublicListItem = {
  name: string;
  detail: string;
  bottle_price_cents: number;
  glass_price_cents: number;
  currency: string;
};

export type PublicListSection = {
  name: string;
  items: PublicListItem[];
};

export type PurchaseApproval = {
  id: string;
  decision: string;
  required_role: string;
  comment: string | null;
  decided_at: string | null;
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

export type PurchaseOrderList = {
  orders: PurchaseOrderRow[];
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

export type QuizAttemptRow = {
  id: string;
  user_id: string;
  name: string;
  staff_name: string;
  score: number;
  score_bp: number;
  answers: number[];
  created_at: string;
};

export type QuizQuestion = {
  id: string;
  prompt: string;
  choices: string[];
  kind?: string;
};

export type QuizReviewItem = {
  id: string;
  prompt: string;
  selected: number;
  ok: boolean;
  explain: string;
};

export type ReadingBody = {
  temp_c: unknown;
  humidity_pct: unknown;
  notes?: string | null;
  source?: string;
};

export type ReceiptBody = {
  invoice_id?: string | null;
  notes?: string | null;
  lines: ReceiptLineBody[];
};

export type ReceiptLineBody = {
  po_line_id?: string | null;
  sku?: string | null;
  counted_qty: number | string;
  received_vintage?: string | null;
  bin_id?: string | null;
  resolution_note?: string | null;
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

export type ReceiptList = {
  receipts: ReceiptRecord[];
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

export type ReminderDecision = {
  status: string;
  channel: string;
};

export type ReminderList = {
  jurisdiction: string;
  rules: ReminderRule[];
  reminders: ReminderRecord[];
  channel: string;
};

export type ReminderRecord = {
  source_type: string;
  source_id: string;
  rule_code: string;
  title: string;
  detail: string;
  due_on: string;
  days_left: number;
  label: string;
  channel: string;
};

export type ReminderRule = {
  code: string;
  title: string;
  detail: string;
  lead_days?: number;
  applies_to?: string;
  jurisdiction?: string;
};

export type RemovedId = {
  removed: string;
};

export type RemovedMember = {
  removed: boolean;
  user_id: string;
};

export type RepFollowup = {
  id: string;
  session_id: string;
  supplier_id: string | null;
  supplier: string;
  to_email: string;
  subject: string;
  body: string;
  purchase_order_id: string | null;
  purchase_order_number: string;
  mailto: string;
  sent: boolean;
};

export type RepFollowupDraft = {
  followup: RepFollowup;
};

export type RepFollowupEnvelope = {
  followup: RepFollowup | null;
};

export type ResolveBody = {
  resolved_quantity: number | string;
  notes?: string | null;
};

export type RetentionBody = {
  document_retention_years: number;
};

export type RetentionPolicy = {
  document_retention_years: number;
  can_edit: boolean;
};

export type RoleplayCriterion = {
  pass: boolean;
  evidence: string;
};

export type RoleplayReply = {
  text: string;
};

export type RoleplayResponse = {
  session: RoleplaySession;
};

export type RoleplayRubric = {
  listened: RoleplayCriterion;
  offered_two_options: RoleplayCriterion;
  described_structure: RoleplayCriterion;
  handled_price: RoleplayCriterion;
};

export type RoleplaySession = {
  id: string;
  persona: string;
  dish_id: string | null;
  dish_name: string;
  status: "open" | "scored";
  transcript: RoleplayTurn[];
  rubric: RoleplayRubric | null;
  score: number | null;
  started_at: string | null;
  scored_at: string | null;
};

export type RoleplayStart = {
  persona?: string;
  dish_id?: string | null;
  dish?: string;
};

export type RoleplayTurn = {
  role: "guest" | "staff";
  text: string;
  product_ids?: string[];
};

export type SampleBody = {
  product_id?: string | null;
  sku_id?: string | null;
  supplier_id?: string | null;
  offer_id?: string | null;
  note?: string;
  quoted_price_cents?: number | null;
  currency?: string | null;
};

export type SampleCard = {
  id: string;
  session_id: string;
  product_id: string | null;
  product_name: string;
  sku_id: string | null;
  supplier_id: string | null;
  supplier: string;
  offer_id: string | null;
  label_document_id: string | null;
  matched: boolean;
  score: number | null;
  note: string;
  quoted_price_cents: number | null;
  currency: string | null;
  quoted_label: string;
  decision: "undecided" | "buy" | "list" | "pass";
  pass_reason: string;
  purchase_order_id: string | null;
  purchase_order_number: string;
  purchase_order_status: string;
  list_id: string | null;
  list_version_id: string | null;
  list_version_number: number | null;
  list_price: SampleListPrice;
  pairs_with: SamplePairs;
};

export type SampleDish = {
  dish_id: string;
  name: string;
  course: string;
  score: number;
  confidence: string;
};

export type SampleEnvelope = {
  sample: SampleCard;
};

export type SampleListPrice = {
  bottle_price: number | null;
  glass_price: number | null;
  bottle_label: string;
  glass_label: string;
  margin_pct: number | null;
  margin_label: string;
  cost_cents: number | null;
  cost_label: string;
  currency: string;
  source: string;
  note: string;
};

export type SampleMenu = {
  text: string;
};

export type SamplePairs = {
  profile: string;
  note: string;
  dishes: SampleDish[];
};

export type SamplePatch = {
  product_id?: string | null;
  sku_id?: string | null;
  supplier_id?: string | null;
  offer_id?: string | null;
  note?: string | null;
  quoted_price_cents?: number | null;
  currency?: string | null;
  score?: number | null;
  decision?: string | null;
};

export type ScoreBody = {
  score?: number | null;
  note?: string | null;
};

export type SectionBody = {
  name: string;
  position?: number;
  budget_share_pct?: number | null;
};

export type SectionsBody = {
  sections: SectionBody[];
};

export type SensorBody = {
  name: string;
  zone_id: string;
  metric: string;
  external_id: string;
};

export type SensorImport = {
  id: string;
  filename: string;
  status: string;
  rows: SensorImportRow[];
  posted?: number;
  skipped?: number;
  excursions?: number;
};

export type SensorImportList = {
  imports: SensorImport[];
};

export type SensorImportRow = {
  line: number;
  sensor: string;
  external_id: string;
  at: string;
  metric: string;
  value: string;
  zone: string;
  excursion: string;
  duplicate: boolean;
  error: string;
};

export type SensorList = {
  sensors: SensorRecord[];
  stale_after_hours: number;
};

export type SensorRecord = {
  id: string;
  name: string;
  zone_id: string;
  zone_name: string;
  location_name: string;
  metric: string;
  external_id: string;
  sensor_key: string;
  secret_last4: string;
  masked: string;
  last_value: string;
  last_at: string | null;
  stale: boolean;
  stale_after_hours: number;
  secret?: string;
};

export type ServiceCardList = {
  service_cards: ServiceCardRecord[];
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

export type SessionBody = {
  supplier_id?: string | null;
  supplier_name?: string;
  title?: string;
  starts_at?: string;
  ends_at?: string;
  when?: string;
  location?: string;
  notes?: string;
  status?: string;
};

export type SessionPatch = {
  supplier_id?: string | null;
  title?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  when?: string | null;
  location?: string | null;
  notes?: string | null;
  status?: string | null;
};

export type SettingsSaveBody = {
  provider: string;
  model?: string;
  api_key?: string;
};

export type SkuList = {
  skus: CatalogSku[];
};

export type SourcingBrief = {
  id: string;
  list_id: string | null;
  title: string;
  status: string;
  items: SourcingBriefItem[];
};

export type SourcingBriefEnvelope = {
  brief: SourcingBrief;
};

export type SourcingBriefItem = {
  id: string;
  category: string;
  style: string;
  price_band: string;
  quantity_hint: number;
  dishes: SourcingDish[];
  sample_id: string | null;
  offer_id: string | null;
  rationale: string;
  position: number;
};

export type SourcingBriefList = {
  briefs: SourcingBrief[];
};

export type SourcingDish = {
  dish_id: string;
  name: string;
};

export type SquareConnectBody = {
  access_token?: string;
  location_id?: string;
};

export type StandardBody = {
  slug: string;
  title: string;
  body: string;
  topic?: string | null;
};

export type StandardList = {
  can_author: boolean;
  standards: ServiceStandard[];
};

export type StartBody = {
  location_id: string;
  notes?: string;
};

export type StatusPayload = {
  app: string;
  demo_mode: boolean;
  llm_provider: string;
  llm_model: string;
  llm_source: string;
  label: string;
  database: string;
  specialists: string[];
  sample_menu?: string;
  wiring?: WiringStatus | null;
  wiring_error?: string;
};

export type StockBody = {
  on_hand: number | string;
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

export type StockLocation = {
  location_id: string;
  location_name: string;
  quantity: number;
  valuation_cents: number;
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

export type StorageAlert = {
  id: string;
  zone: string;
  metric: string;
  status: string;
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

export type StorageZoneEnvelope = {
  zone: StorageZone;
};

export type StorageZoneList = {
  zones: StorageZone[];
};

export type SupplierBody = {
  name: string;
  kind?: string;
  contact_email?: string;
  account_number?: string | null;
  order_minimum_cents?: number;
  default_case_size?: number;
  delivery_days?: string[];
  lead_time_days?: number;
  payment_terms?: string | null;
  notes?: string | null;
};

export type SupplierContactRow = {
  id: string;
  supplier_id: string;
  name: string;
  role: string | null;
  email: string;
  phone: string | null;
  is_primary: boolean;
};

export type SupplierDeskPayload = {
  supplier: SupplierProfile;
  allocations: AllocationRecord[];
  offers: OfferRecord[];
  current_offers: OfferRecord[];
  price_sheets: PriceSheetRecord[];
  products: CatalogChoice[];
};

export type SupplierEnvelope = {
  supplier: SupplierRow;
};

export type SupplierList = {
  suppliers: SupplierRow[];
};

export type SupplierName = {
  id: string;
  name: string;
  kind?: string;
  contact_email?: string | null;
  notes?: string;
};

export type SupplierNameList = {
  suppliers: SupplierName[];
};

export type SupplierProfile = {
  id: string;
  name: string;
  kind: string;
  rep_name: string;
  rep_email: string;
  rep_phone: string | null;
  delivery_days: string[];
  order_minimum_cents: number;
  order_minimum_currency: string;
  order_minimum_label: string;
  payment_terms: string | null;
  notes: string;
  lead_time_days: number;
  default_case_size: number;
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

export type SyncBody = {
  entries?: SyncEntry[];
};

export type SyncEntry = {
  client_mutation_id: string;
  device_id?: string;
  sku?: string | null;
  barcode?: string | null;
  bin_qr?: string | null;
  bin_id?: string | null;
  counted_quantity: number | string;
  counted_at?: string | null;
  notes?: string | null;
};

export type TastingCreateResult = {
  draft: TastingDraftCard;
};

export type TastingDraft = {
  note: TastingNote;
  service_card: ServiceCardRecord;
};

export type TastingDraftCard = {
  id: string;
  title: string;
  ics: string;
  sent: boolean;
};

export type TastingHistory = {
  rows: TastingHistoryRow[];
};

export type TastingHistoryRow = {
  supplier_id: string;
  supplier: string;
  product_id: string;
  product: string;
  tasted: number;
  buy: number;
  list: number;
  pass: number;
  undecided: number;
  bought_bottles: number;
  invoiced_bottles: number;
  last_cost_cents: number | null;
  last_cost_label: string;
};

export type TastingInvite = {
  id: string;
  session_id: string;
  title: string;
  supplier: string;
  status: string;
  agenda_note: string;
  agenda_facts: InviteFacts;
  slots: InviteSlot[];
  attendees: InviteAttendee[];
  approval: InviteApproval | null;
  chosen_starts_at: string;
  email_subject: string;
  email_body: string;
  email_mailto: string;
  sent: boolean;
  driver: string;
  ics_ready: boolean;
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

export type TastingNoteList = {
  notes: TastingNote[];
};

export type TastingSessionDetail = {
  session: TastingSessionRow;
  samples: SampleCard[];
};

export type TastingSessionList = {
  sessions: TastingSessionRow[];
};

export type TastingSessionRow = {
  id: string;
  supplier_id: string | null;
  supplier: string;
  title: string;
  starts_at: string;
  ends_at: string;
  location: string;
  status: string;
  notes: string;
  sample_count: number;
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

export type TeamMember = {
  membership_id: string;
  user_id: string;
  name: string;
  email: string;
  role: string;
  position: string | null;
};

export type TeamPerson = {
  user_id: string;
  name: string;
  email: string;
  role: string;
  position: string | null;
  briefing_ack: BriefingAckStat;
  lessons_done: number;
  quiz_average_bp: number | null;
  quiz_average_label: string;
  roleplay_average_bp: number | null;
  roleplay_average_label: string;
};

export type TeamProgress = {
  week: TeamWeek;
  people: TeamPerson[];
  weak_topics: WeakTopic[];
  expiring_certificates: CertificateRecord[];
};

export type TeamRoster = {
  members: TeamMember[];
  invites: TeamInvite[];
};

export type TeamWeek = {
  start: string;
  end: string;
};

export type TonightApproval = {
  id: string;
  kind: string;
  title: string;
  status: string;
  href?: string;
};

export type TonightBoard = {
  service_date: string;
  briefing_hour: number;
  timezone: string;
  available: boolean;
  role: string;
  briefing: TonightBriefing | null;
  low_stock: LowStockRow[];
  storage_alerts: StorageAlert[];
  deliveries_due: DeliveryDue[];
  approvals: TonightApproval[];
  pos_alerts?: PosAlert[];
  sensors?: SensorRecord[];
  reminders?: ReminderRecord[];
  expiring_certificates: CertificateGap[];
};

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

export type TonightEnvelope = {
  role: string;
  available: boolean;
  ready: boolean;
  service_date: string;
  timezone: string;
  briefing_hour: number;
  briefing: TonightBriefing | null;
};

export type TrainingLesson = {
  id: string;
  slug: string;
  title: string;
  body: string;
  position: string;
  status: string;
  can_author: boolean;
  quiz_id: string | null;
  standards: LessonStandard[];
  bottles: LessonBottle[];
};

export type TrainingLessons = {
  role: string;
  name: string;
  position: string | null;
  can_author: boolean;
  lessons: TrainingLesson[];
  drafts: TrainingLesson[];
};

export type TrainingOverview = {
  lessons: TrainingLesson[];
  quiz?: unknown;
  roleplay?: unknown;
};

export type TrainingProgress = {
  attempts: QuizAttemptRow[];
};

export type TrainingQuiz = {
  id: string;
  lesson_id?: string | null;
  title: string;
  questions: QuizQuestion[];
  score?: number | null;
  score_bp?: number | null;
  correct?: number | null;
  total?: number | null;
  review?: QuizReviewItem[];
  next_review_at?: string | null;
  next_review_on?: string | null;
};

export type TransferBody = {
  sku: string;
  from_location_id: string;
  to_location_id: string;
  quantity: number | string;
  from_bin_id?: string | null;
  to_bin_id?: string | null;
  reason?: string | null;
};

export type UsageByAgent = {
  subagent: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  cost_micro_usd: number;
};

export type UsageByDay = {
  day: string;
  calls: number;
  cost_micro_usd: number;
};

export type UsageReport = {
  month: string;
  monthly_spend_cap_cents: number | null;
  spent_cents: number;
  spent_micro_usd: number;
  requests_per_minute: number | null;
  requests_this_minute: number;
  by_subagent: UsageByAgent[];
  by_day: UsageByDay[];
  cap_status: string;
  can_edit: boolean;
  demo: boolean;
};

export type ValidationError = {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

export type VarianceLine = {
  sku: string;
  name: string;
  counted_quantity: number | null;
  expected_quantity: number;
  variance: number | null;
  variance_value_cents: number | null;
  unit_cost_cents: number;
};

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

export type WantLink = {
  sample_id?: string | null;
  offer_id?: string | null;
  clear_sample?: boolean;
  clear_offer?: boolean;
};

export type WeakTopic = {
  topic: string;
  correct: number;
  total: number;
  accuracy_bp: number;
  label: string;
};

export type WebhookReading = {
  status: string;
  reading_id?: string;
  excursion?: boolean;
};

export type WebhookResult = {
  accepted: number;
  duplicates: number;
  readings?: WebhookReading[];
};

export type WiringStatus = {
  specialists: string[];
  has_task_tool: boolean;
  expected: string[];
};

export type ZoneBody = {
  name: string;
  location_id?: string | null;
  target_temp_min_c: unknown;
  target_temp_max_c: unknown;
  target_humidity_min_pct: unknown;
  target_humidity_max_pct: unknown;
  notes?: string | null;
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

export type ZoneExcursionEnvelope = {
  excursion: ZoneExcursion;
};

export type ZoneExcursionList = {
  excursions: ZoneExcursion[];
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

export type ZoneReadingList = {
  readings: ZoneReading[];
};

export type ZoneReadingResult = {
  reading: ZoneReading;
  excursion: ZoneExcursion | null;
  zone: StorageZone;
};

export type madira__api__inventory__LocationBody = {
  name: string;
  kind?: string;
  notes?: string;
};

export type madira__api__lists__DecisionBody = {
  comment?: string | null;
};

export type madira__api__pos__LocationBody = {
  location_id: string;
};

export type madira__api__purchasing__DecisionBody = {
  comment?: string | null;
};

export type madira__api__tastings__DecisionBody = {
  decision: string;
  reason?: string;
};

export type AguiThreadMessagesAgUiThreadsThreadIdMessagesGetResponse = AguiMessages;
export type AuthCallbackAuthCallbackGetResponse = unknown;
export type AuthConfigAuthConfigGetResponse = AuthConfig;
export type AuthCsrfAuthCsrfGetResponse = OkResponse;
export type AuthDemoPersonaAuthDemoPersonaPostResponse = DemoPersona;
export type AuthDemoPersonasAuthDemoPersonasGetResponse = DemoPersonaList;
export type AuthGoogleAuthGoogleGetResponse = unknown;
export type AuthLogoutAuthLogoutPostResponse = OkResponse;
export type AuthMeAuthMeGetResponse = AccountEnvelope;
export type CellarClearEightySixCellarSkusSkuId86DeleteResponse = EightySixResult;
export type CellarEightySixCellarSkusSkuId86PostResponse = EightySixResult;
export type AuditEventsComplianceAuditEventsGetResponse = AuditEventList;
export type AuditVerifyComplianceAuditEventsVerifyGetResponse = AuditChain;
export type AuditPackExportComplianceAuditPackExportGetResponse = unknown;
export type AuditPackPreviewComplianceAuditPackPreviewGetResponse = AuditPackPreview;
export type DocumentsComplianceDocumentsGetResponse = DocumentList;
export type DocumentsUploadComplianceDocumentsPostResponse = DocumentEnvelope;
export type DocumentsDownloadComplianceDocumentsDocumentIdDownloadGetResponse = unknown;
export type GapsComplianceGapsGetResponse = ComplianceGaps;
export type QueryComplianceComplianceQueriesComplianceGetResponse = AuditorQuery;
export type QueryConditionsComplianceQueriesConditionsGetResponse = AuditorQuery;
export type QueryEventsComplianceQueriesEventsGetResponse = AuditorQuery;
export type QueryListsComplianceQueriesListsGetResponse = AuditorQuery;
export type QueryPosComplianceQueriesPosGetResponse = AuditorQuery;
export type QueryPurchasesComplianceQueriesPurchasesGetResponse = AuditorQuery;
export type QueryStockComplianceQueriesStockGetResponse = AuditorQuery;
export type RetentionGetComplianceRetentionGetResponse = RetentionPolicy;
export type RetentionPatchComplianceRetentionPatchResponse = RetentionPolicy;
export type SampleMenuFixturesSampleMenuGetResponse = SampleMenu;
export type HealthHealthGetResponse = HealthPayload;
export type InventoryInventoryGetResponse = CellarBoard;
export type InventoryBinsInventoryBinsGetResponse = BinList;
export type InventoryBinCreateInventoryBinsPostResponse = BinEnvelope;
export type InventoryBinQrInventoryBinsBinIdQrGetResponse = BinLabel;
export type InventoryCountsInventoryCountsGetResponse = CountSessionList;
export type InventoryCountStartInventoryCountsPostResponse = CountSessionRecord;
export type InventoryCountGetInventoryCountsSessionIdGetResponse = CountReport;
export type InventoryCountApproveInventoryCountsSessionIdApprovePostResponse = CountReport;
export type InventoryCountResolveInventoryCountsSessionIdConflictsSkuResolvePostResponse = CountReport;
export type InventoryCountSubmitInventoryCountsSessionIdSubmitPostResponse = CountReport;
export type InventoryCountSyncInventoryCountsSessionIdSyncPostResponse = CountReport;
export type StorageExcursionsInventoryExcursionsGetResponse = ZoneExcursionList;
export type StorageExcursionAcknowledgeInventoryExcursionsExcursionIdAcknowledgePostResponse = ZoneExcursionEnvelope;
export type InventoryLocationsInventoryLocationsGetResponse = LocationList;
export type InventoryLocationCreateInventoryLocationsPostResponse = LocationEnvelope;
export type InventoryMovementsInventoryMovementsGetResponse = MovementList;
export type InventoryMovementCreateInventoryMovementsPostResponse = MovementEnvelope;
export type InventoryParListInventoryParProposalsGetResponse = ParProposalList;
export type InventoryParGenerateInventoryParProposalsGeneratePostResponse = ParProposalList;
export type InventoryParAcceptInventoryParProposalsProposalIdAcceptPostResponse = ParProposalEnvelope;
export type InventoryParRejectInventoryParProposalsProposalIdRejectPostResponse = ParProposalEnvelope;
export type StorageZonesInventoryStorageZonesGetResponse = StorageZoneList;
export type StorageZoneCreateInventoryStorageZonesPostResponse = StorageZoneEnvelope;
export type StorageReadingsInventoryStorageZonesZoneIdReadingsGetResponse = ZoneReadingList;
export type StorageReadingCreateInventoryStorageZonesZoneIdReadingsPostResponse = ZoneReadingResult;
export type InventoryTransferInventoryTransfersPostResponse = MovementList;
export type InventoryPatchInventorySkuPatchResponse = CellarBoard;
export type AddLicenseLicensesPostResponse = LicenseRecorded;
export type ListsListsGetResponse = ListIndex;
export type ListsCurateListsCuratePostResponse = BeverageListDetail;
export type ImportListListsImportPostResponse = ListImportResult;
export type GetPricingRulesListsPricingRulesGetResponse = PricingRulesResponse;
export type PutPricingRulesListsPricingRulesPutResponse = PricingRulesResponse;
export type GetListVersionListsVersionsVersionIdGetResponse = ListVersionRecord;
export type PostListVersionApproveListsVersionsVersionIdApprovePostResponse = ListVersionRecord;
export type GetListVersionDiffListsVersionsVersionIdDiffGetResponse = ListDiff;
export type GetListVersionPdfListsVersionsVersionIdPdfGetResponse = unknown;
export type GetListVersionQrListsVersionsVersionIdQrPngGetResponse = unknown;
export type PostListVersionRejectListsVersionsVersionIdRejectPostResponse = ListVersionRecord;
export type PostListVersionRevokeListsVersionsVersionIdRevokePublicPostResponse = ListVersionRecord;
export type PostListVersionSubmitListsVersionsVersionIdSubmitPostResponse = ListVersionRecord;
export type ListCoverageListsListIdCoverageGetResponse = ListCoverage;
export type ListHealthRouteListsListIdHealthGetResponse = ListHealth;
export type PostItemListsListIdItemsPostResponse = BeverageListDetail;
export type DeleteItemListsListIdItemsItemIdDeleteResponse = BeverageListDetail;
export type PatchItemListsListIdItemsItemIdPatchResponse = BeverageListDetail;
export type PutSectionsListsListIdSectionsPutResponse = BeverageListDetail;
export type GetListVersionsListsListIdVersionsGetResponse = ListVersionIndex;
export type PostListVersionListsListIdVersionsPostResponse = ListVersionRecord;
export type FloorLookupLookupGetResponse = LookupResult;
export type LookupPackLookupPackGetResponse = LookupPack;
export type ListMenusRouteMenusGetResponse = MenuList;
export type UploadMenuMenusIngestPostResponse = MenuIngestResult;
export type ParseMenuRouteMenusParsePostResponse = MenuParseResult;
export type UploadMenuMenusUploadPostResponse = MenuIngestResult;
export type GetMenuRouteMenusMenuIdGetResponse = MenuDetail;
export type PairMenuMenusMenuIdPairPostResponse = PairingGridResult;
export type GetPairingsMenusMenuIdPairingsGetResponse = PairingGridResult;
export type PinPairingRouteMenusMenuIdPairingsPairingIdPinPostResponse = PairingGridResult;
export type RejectPairingRouteMenusMenuIdPairingsPairingIdRejectPostResponse = PairingGridResult;
export type SwapPairingRouteMenusMenuIdPairingsPairingIdSwapPostResponse = PairingGridResult;
export type ConfirmMenuMenusMenuIdVersionsVersionIdConfirmPostResponse = MenuIngestResult;
export type EditDishRouteMenusMenuIdVersionsVersionIdDishesDishIdPatchResponse = MenuIngestResult;
export type PosCatalogPosCatalogGetResponse = PosCatalog;
export type PosConnectDemoPosConnectDemoPostResponse = PosStatus;
export type PosConnectSquarePosConnectSquarePostResponse = PosStatus;
export type PosGapsPosGapsGetResponse = PosGapList;
export type PosLocationPosLocationPostResponse = PosStatus;
export type PosMappingsPosMappingsGetResponse = PosMappingList;
export type PosSaveMappingPosMappingsPostResponse = PosMappingEnvelope;
export type PosRemoveMappingPosMappingsMappingIdDeleteResponse = RemovedId;
export type PosRunsPosRunsGetResponse = PosRunList;
export type PosStatusPosStatusGetResponse = PosStatus;
export type PosSyncPosSyncPostResponse = PosSyncResult;
export type DeleteAllocationProcurementAllocationsAllocationIdDeleteResponse = DeletedId;
export type UpdateAllocationProcurementAllocationsAllocationIdPatchResponse = AllocationEnvelope;
export type ProcurementInvoicesProcurementInvoicesGetResponse = InvoiceList;
export type ProcurementInvoiceGetProcurementInvoicesInvoiceIdGetResponse = InvoiceRecord;
export type ProcurementInvoiceDocumentProcurementInvoicesInvoiceIdDocumentGetResponse = unknown;
export type ListOffersProcurementOffersGetResponse = OfferList;
export type CreateOfferProcurementOffersPostResponse = OfferEnvelope;
export type DeleteOfferProcurementOffersOfferIdDeleteResponse = DeletedId;
export type UpdateOfferProcurementOffersOfferIdPatchResponse = OfferEnvelope;
export type ProcurementOrdersProcurementOrdersGetResponse = PurchaseOrderList;
export type ProcurementOrderCreateProcurementOrdersPostResponse = PurchaseOrderRow;
export type ProcurementDraftReorderProcurementOrdersDraftFromReorderPostResponse = PurchaseOrderList;
export type ProcurementOrderGetProcurementOrdersPoIdGetResponse = PurchaseOrderRow;
export type ProcurementOrderApproveProcurementOrdersPoIdApprovePostResponse = PurchaseOrderRow;
export type ProcurementOrderCancelProcurementOrdersPoIdCancelPostResponse = PurchaseOrderRow;
export type ProcurementOrderCloseProcurementOrdersPoIdClosePostResponse = PurchaseOrderRow;
export type ProcurementInvoiceUploadProcurementOrdersPoIdInvoicesPostResponse = InvoiceRecord;
export type ProcurementOrderPdfProcurementOrdersPoIdPdfGetResponse = unknown;
export type ProcurementReceiptStageProcurementOrdersPoIdReceiptsPostResponse = ReceiptRecord;
export type ProcurementOrderRejectProcurementOrdersPoIdRejectPostResponse = PurchaseOrderRow;
export type ProcurementOrderSendProcurementOrdersPoIdSendPostResponse = PurchaseOrderRow;
export type UploadPriceSheetProcurementPriceSheetsPostResponse = PriceSheetEnvelope;
export type GetPriceSheetProcurementPriceSheetsSheetIdGetResponse = PriceSheetEnvelope;
export type ApplyPriceSheetProcurementPriceSheetsSheetIdApplyPostResponse = PriceSheetApplied;
export type RejectPriceSheetProcurementPriceSheetsSheetIdRejectPostResponse = PriceSheetApplied;
export type PriceHistoryProcurementProductsProductIdPriceHistoryGetResponse = PriceHistory;
export type ProcurementReceiptsProcurementReceiptsGetResponse = ReceiptList;
export type ProcurementReceiptGetProcurementReceiptsReceiptIdGetResponse = ReceiptRecord;
export type ProcurementReceiptAcceptProcurementReceiptsReceiptIdAcceptPostResponse = ReceiptRecord;
export type ProcurementSuppliersProcurementSuppliersGetResponse = SupplierList;
export type ProcurementSupplierCreateProcurementSuppliersPostResponse = SupplierEnvelope;
export type CreateAllocationProcurementSuppliersSupplierIdAllocationsPostResponse = AllocationEnvelope;
export type ProcurementContactCreateProcurementSuppliersSupplierIdContactsPostResponse = ContactEnvelope;
export type SupplierDeskProcurementSuppliersSupplierIdDeskGetResponse = SupplierDeskPayload;
export type UpdateProfileProcurementSuppliersSupplierIdProfilePatchResponse = ProfileEnvelope;
export type ProductsProductsGetResponse = ProductList;
export type ProductProductsProductIdGetResponse = CatalogProduct;
export type NotesProductsProductIdNotesGetResponse = TastingNoteList;
export type CreateNoteProductsProductIdNotesPostResponse = TastingDraft;
export type CreateDraftProductsProductIdNotesDraftPostResponse = TastingDraft;
export type NoteProductsProductIdNotesNoteIdGetResponse = TastingNote;
export type UpdateNoteProductsProductIdNotesNoteIdPatchResponse = TastingNote;
export type ApproveOneNoteProductsProductIdNotesNoteIdApprovePostResponse = TastingNote;
export type CardsProductsProductIdServiceCardsGetResponse = ServiceCardList;
export type CardProductsProductIdServiceCardsCardIdGetResponse = ServiceCardRecord;
export type UpdateCardProductsProductIdServiceCardsCardIdPatchResponse = ServiceCardRecord;
export type ApproveOneCardProductsProductIdServiceCardsCardIdApprovePostResponse = ServiceCardRecord;
export type GetPublicListPublicListsTokenGetResponse = PublicList;
export type PoListPurchaseOrdersGetResponse = PurchaseOrderList;
export type PoDraftPurchaseOrdersDraftPostResponse = PurchaseOrderList;
export type RemindersRemindersGetResponse = ReminderList;
export type DecideReminderRemindersDecidePostResponse = ReminderDecision;
export type SensorsSensorsGetResponse = SensorList;
export type AddSensorSensorsPostResponse = SensorRecord;
export type ImportsSensorsImportsGetResponse = SensorImportList;
export type UploadCsvSensorsImportsPostResponse = SensorImport;
export type ApplyCsvSensorsImportsImportIdApplyPostResponse = SensorImport;
export type RejectCsvSensorsImportsImportIdRejectPostResponse = SensorImport;
export type WebhookSensorsWebhookSensorKeyPostResponse = WebhookResult;
export type RotateSensorsSensorIdRotatePostResponse = SensorRecord;
export type SettingsDeleteSettingsLlmDeleteResponse = LlmSettings;
export type SettingsGetSettingsLlmGetResponse = LlmSettings;
export type SettingsSaveSettingsLlmPostResponse = LlmSettings;
export type SkusSkusGetResponse = SkuList;
export type SkuSkusSkuIdGetResponse = CatalogSku;
export type SourcingBriefsSourcingBriefsGetResponse = SourcingBriefList;
export type SourcingBriefsCreateSourcingBriefsPostResponse = SourcingBriefEnvelope;
export type SourcingBriefSourcingBriefsBriefIdGetResponse = SourcingBriefEnvelope;
export type SourcingHistorySourcingHistoryGetResponse = TastingHistory;
export type SourcingItemSourcingItemsItemIdPatchResponse = SourcingBriefEnvelope;
export type StatusStatusGetResponse = StatusPayload;
export type SuppliersSuppliersGetResponse = SupplierNameList;
export type TastingsTastingsGetResponse = TastingSessionList;
export type TastingsCreateTastingsPostResponse = TastingCreateResult;
export type TastingDeleteTastingsSessionIdDeleteResponse = DeletedId;
export type TastingGetTastingsSessionIdGetResponse = TastingSessionDetail;
export type TastingPatchTastingsSessionIdPatchResponse = TastingSessionDetail;
export type TastingIcsTastingsSessionIdIcsGetResponse = unknown;
export type TastingFollowupTastingsSessionIdFollowUpGetResponse = RepFollowupEnvelope;
export type TastingFollowupDraftTastingsSessionIdFollowUpPostResponse = RepFollowupDraft;
export type TastingInviteTastingsSessionIdInviteGetResponse = InviteDesk;
export type TastingInviteProposeTastingsSessionIdInvitePostResponse = InviteDesk;
export type TastingInviteIcsTastingsSessionIdInviteIcsGetResponse = unknown;
export type TastingInviteApproveTastingsSessionIdInviteApprovePostResponse = InviteDesk;
export type TastingInviteRejectTastingsSessionIdInviteRejectPostResponse = InviteDesk;
export type SamplesCreateTastingsSessionIdSamplesPostResponse = SampleEnvelope;
export type SamplesLabelTastingsSessionIdSamplesLabelPostResponse = SampleEnvelope;
export type SamplesDeleteTastingsSessionIdSamplesSampleIdDeleteResponse = DeletedId;
export type SamplesPatchTastingsSessionIdSamplesSampleIdPatchResponse = SampleEnvelope;
export type SamplesDecisionTastingsSessionIdSamplesSampleIdDecisionPostResponse = SampleEnvelope;
export type SampleLabelTastingsSessionIdSamplesSampleIdLabelPostResponse = SampleEnvelope;
export type SamplesScoreTastingsSessionIdSamplesSampleIdScorePostResponse = SampleEnvelope;
export type TeamRosterTeamGetResponse = TeamRoster;
export type TeamCertificatesTeamCertificatesGetResponse = CertificateList;
export type TeamCertificateCreateTeamCertificatesPostResponse = CertificateEnvelope;
export type TeamCertificateDeleteTeamCertificatesCertificateIdDeleteResponse = DeletedFlag;
export type TeamCertificateTeamCertificatesCertificateIdGetResponse = CertificateRecord;
export type TeamCertificateUpdateTeamCertificatesCertificateIdPatchResponse = CertificateEnvelope;
export type TeamCertificateDocumentTeamCertificatesCertificateIdDocumentPostResponse = CertificateEnvelope;
export type TeamInviteTeamInvitesPostResponse = TeamInvite;
export type TeamRevokeTeamInvitesInviteIdRevokePostResponse = TeamInvite;
export type TeamRemoveMemberTeamMembersUserIdDeleteResponse = RemovedMember;
export type TeamUpdateMemberTeamMembersUserIdPatchResponse = TeamMember;
export type TeamProgressTeamProgressGetResponse = TeamProgress;
export type TonightBoardTonightGetResponse = TonightBoard;
export type TonightBriefingTonightBriefingGetResponse = TonightEnvelope;
export type TonightPublishTonightBriefingPublishPostResponse = TonightEnvelope;
export type TonightRebuildTonightBriefingRebuildPostResponse = TonightEnvelope;
export type TonightReportTonightBriefingReportGetResponse = BriefingReport;
export type TonightAckTonightBriefingBriefingIdAckPostResponse = TonightBriefing;
export type TrainingTrainingGetResponse = TrainingOverview;
export type TrainingCertificatesTrainingCertificatesGetResponse = CertificateList;
export type TrainingCertificateTrainingCertificatesCertificateIdGetResponse = CertificateRecord;
export type TrainingLessonsTrainingLessonsGetResponse = TrainingLessons;
export type TrainingDraftTrainingLessonsDraftPostResponse = TrainingLesson;
export type TrainingEditTrainingLessonsLessonIdPatchResponse = TrainingLesson;
export type TrainingApproveTrainingLessonsLessonIdApprovePostResponse = TrainingLesson;
export type TrainingProgressTrainingProgressGetResponse = TrainingProgress;
export type TrainingFromListTrainingQuizzesFromListPostResponse = TrainingQuiz;
export type TrainingQuizTrainingQuizzesQuizIdGetResponse = TrainingQuiz;
export type TrainingAttemptTrainingQuizzesQuizIdAttemptsPostResponse = TrainingQuiz;
export type TrainingDueTrainingReviewsDueGetResponse = DueReviewList;
export type TrainingRoleplayTrainingRoleplayPostResponse = RoleplayResponse;
export type TrainingRoleplayReplyTrainingRoleplaySessionIdReplyPostResponse = RoleplayResponse;
export type TrainingRoleplayScoreTrainingRoleplaySessionIdScorePostResponse = RoleplayResponse;
export type TrainingStandardsTrainingStandardsGetResponse = StandardList;
export type TrainingStandardsPutTrainingStandardsPutResponse = ServiceStandard;
export type TrainingStandardsResetTrainingStandardsSlugResetPostResponse = ServiceStandard;
export type GetUsageUsageGetResponse = UsageReport;
export type PutLimitsUsageLimitsPutResponse = UsageReport;
