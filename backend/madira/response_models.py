"""OpenAPI response models for every JSON route.

These classes describe the document ``app.openapi()`` publishes. Route
handlers do not use them as ``response_model``, so a response body is never
validated or rewritten here.

Field defaults mark a property optional in the schema. A default of ``None``
on ``T | None`` is ``field?: T | null``. A default on ``T`` alone is
``field?: T``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class APIModel(BaseModel):
    pass


# --- health, auth, settings -------------------------------------------------

class HealthPayload(APIModel):
    status: str
    app: str
    demo_mode: bool
    llm_provider: str
    llm_model: str
    llm_source: str
    label: str
    database: str


class WiringStatus(APIModel):
    specialists: list[str]
    has_task_tool: bool
    expected: list[str]


class StatusPayload(APIModel):
    app: str
    demo_mode: bool
    llm_provider: str
    llm_model: str
    llm_source: str
    label: str
    database: str
    specialists: list[str]
    sample_menu: str = ""
    wiring: WiringStatus | None = None
    wiring_error: str = ""


class SampleMenu(APIModel):
    text: str


class AuthConfig(APIModel):
    configured: bool


class Account(APIModel):
    name: str
    email: str
    picture: str


class AccountEnvelope(APIModel):
    user: Account | None


class OkResponse(APIModel):
    ok: bool


class DemoPersona(APIModel):
    slug: str
    name: str
    role: str
    position: str | None
    email: str


class DemoPersonaList(APIModel):
    active: str
    personas: list[DemoPersona]


class LlmSettings(APIModel):
    configured: bool
    stored: bool
    provider: str | None
    model: str | None
    key_hint: str | None
    demo_mode: bool
    demo_forced: bool
    source: str
    label: str
    warning: str
    default_models: dict[str, str]


class AguiMessages(APIModel):
    messages: list[dict[str, Any]]


# --- menus ------------------------------------------------------------------

class MenuDish(APIModel):
    id: str
    stable_id: str
    name: str
    course: str
    price: int
    currency: str
    main_component: str
    cooking_method: str
    sauce: str
    richness: int
    acidity: int
    sweetness: int
    spice: int
    umami: int
    allergens: list[str]
    confidence: dict[str, float]
    low_confidence: list[str]
    needs_repairing: bool


class MenuReview(APIModel):
    menu_id: str
    version_id: str
    name: str
    number: int
    status: str
    cuisine: str
    price_tier: str
    dishes: list[MenuDish]


class MenuIngestResult(APIModel):
    menu_id: str
    version_id: str
    name: str
    status: str
    review: MenuReview


class MenuSummary(APIModel):
    id: str
    name: str
    cuisine: str
    price_tier: str
    dish_count: int
    status: str


class MenuList(APIModel):
    menus: list[MenuSummary]


class MenuParseDish(APIModel):
    id: str
    name: str
    course: str
    description: str
    flavor_profile: str
    price: int
    currency: str


class MenuParseResult(APIModel):
    menu_id: str
    name: str
    cuisine: str
    price_tier: str
    dishes: list[MenuParseDish]


class PairingSlot(APIModel):
    id: str
    slot: str
    status: str
    sku_id: str | None
    category: str
    name: str
    producer: str
    region: str
    style: str
    rationale: str
    server_script: str
    confidence: str
    price_tier: str
    glass_price: int
    bottle_price: int
    currency: str
    gap: str


class PairingOption(APIModel):
    sku_id: str
    name: str
    producer: str
    category: str
    style: str


class PairingDish(APIModel):
    id: str
    stable_id: str
    name: str
    dish: str
    course: str
    flavor_profile: str
    price: int
    currency: str
    needs_repairing: bool
    options: list[PairingOption]
    pairings: list[PairingSlot]


class PairingGridResult(APIModel):
    menu_id: str
    menu_name: str
    dishes: list[PairingDish]


class MenuDetailDish(MenuDish):
    description: str = ""
    flavor_profile: str = ""
    content_hash: str = ""
    pairings: list[PairingSlot] = Field(default_factory=list)


class MenuDetail(APIModel):
    id: str
    name: str
    cuisine: str
    price_tier: str
    raw_text: str
    version_id: str | None
    version_number: int | None
    status: str
    dishes: list[MenuDetailDish]


# --- lists ------------------------------------------------------------------

class PricingRule(APIModel):
    id: str | None
    category: str
    cost_min_cents: int
    cost_max_cents: int | None
    bottle_multiple: float
    glass_pours_per_bottle: int
    glass_multiple: float
    round_to_cents: int


class PricingRulesResponse(APIModel):
    source: str
    rules: list[PricingRule]


class ListItemRecord(APIModel):
    id: str
    sku_id: str
    product_id: str | None
    list_id: str
    section: str
    section_id: str | None
    position: int
    category: str
    name: str
    producer: str
    region: str
    style: str
    vintage: str
    cost: int = 0
    pour_price: int
    bottle_price: int
    currency: str
    margin_pct: float = 0
    beverage_cost_pct: float = 0
    rule_bottle_price: int = 0
    rule_glass_price: int = 0
    line_cost: int = 0
    band: str


class ListSectionRecord(APIModel):
    id: str
    name: str
    position: int
    budget_share_pct: float | None
    spend: int = 0
    item_count: int
    margin_pct: float = 0
    beverage_cost_pct: float = 0


class CoverageCell(APIModel):
    category: str
    style: str
    band: str
    status: str
    product_id: str | None
    sku_id: str | None
    name: str
    dish_id: str | None
    dish_name: str


class ListCandidate(APIModel):
    sku_id: str
    product_id: str
    name: str
    category: str
    style: str
    band: str
    cost: int = 0


class HealthFlag(APIModel):
    code: str
    message: str
    dish_id: str | None
    item_id: str | None
    sku_id: str | None
    section: str


class ListHealth(APIModel):
    list_id: str
    flags: list[HealthFlag]


class BeverageListDetail(APIModel):
    id: str
    list_id: str
    name: str
    budget: int
    spent: int
    remaining: int
    currency: str
    target_margin: float
    target_beverage_cost_pct: float | None
    concept: str
    price_tier: str
    notes: str
    item_count: int
    items: list[ListItemRecord]
    sections: list[ListSectionRecord]
    cells: list[CoverageCell]
    suggestions: list[CoverageCell]
    gaps: list[str]
    health: ListHealth
    candidates: list[ListCandidate]
    bottles: int
    capacity_bottles: int | None


class ListIndex(APIModel):
    lists: list[BeverageListDetail]


class ListCoverage(APIModel):
    filled: int
    open: int
    cells: list[CoverageCell]
    suggestions: list[CoverageCell]
    list_id: str


class ListImportRow(APIModel):
    line: int
    status: Literal["match", "new", "error"]
    action: str
    message: str
    section: str
    name: str
    producer: str
    category: str
    vintage: str
    bottle_size: str


class ListImportItem(APIModel):
    section: str
    name: str
    producer: str
    vintage: str
    bottle_size: str
    category: str
    pour_price: int
    bottle_price: int
    cost: int
    currency: str
    product_id: str = ""


class ListImportSaved(APIModel):
    id: str
    name: str
    currency: str
    item_count: int
    source_filename: str
    items: list[ListImportItem]


class ListImportResult(APIModel):
    mode: Literal["preview", "confirmed"]
    currency: str
    matched: int
    new: int
    new_products: int
    new_variants: int
    errors: int
    rows: list[ListImportRow]
    saved_list: ListImportSaved | None = Field(default=None, alias="list")


class ListDiffRow(APIModel):
    sku_id: str
    name: str
    section: str
    position: int
    bottle_price_cents: int
    glass_price_cents: int
    currency: str
    previous_bottle_price_cents: int = 0
    previous_glass_price_cents: int = 0
    previous_section: str = ""
    previous_position: int = 0


class ListDiff(APIModel):
    added: list[ListDiffRow]
    removed: list[ListDiffRow]
    repriced: list[ListDiffRow]
    moved: list[ListDiffRow]


class ListVersionApproval(APIModel):
    id: str = ""
    decision: str = ""
    required_role: str = ""
    comment: str | None = None
    decided_at: str | None = None


class ListVersionRecord(APIModel):
    id: str
    list_id: str
    list_name: str
    number: int
    status: str
    can_submit: bool
    can_decide: bool
    public_path: str | None
    public_token: str | None
    approval: ListVersionApproval | None
    diff: ListDiff


class ListVersionIndex(APIModel):
    list_id: str
    can_submit: bool
    versions: list[ListVersionRecord]


class PublicListItem(APIModel):
    name: str
    detail: str
    bottle_price_cents: int
    glass_price_cents: int
    currency: str


class PublicListSection(APIModel):
    name: str
    items: list[PublicListItem]


class PublicListBody(APIModel):
    list_name: str
    number: int
    currency: str
    sections: list[PublicListSection]


class PublicList(APIModel):
    venue_name: str
    published_at: str | None
    rendered: PublicListBody = Field(alias="list")


# --- catalog and notes ------------------------------------------------------

class CatalogVariant(APIModel):
    id: str
    vintage: str
    bottle_size: str
    sku_id: str


class CatalogProduct(APIModel):
    id: str
    category: str
    producer: str
    name: str
    region: str
    country: str
    style: str
    grape: str
    body: str
    acidity: str
    tannin: str
    sweetness: str
    oak: str
    intensity: str
    aroma_families: list[str]
    variants: list[CatalogVariant]


class ProductList(APIModel):
    products: list[CatalogProduct]


class CatalogSku(APIModel):
    id: str
    product_id: str
    variant_id: str
    barcode: str
    bin_label: str
    par: int
    cost: int
    currency: str
    vintage: str
    bottle_size: str
    category: str
    producer: str
    name: str
    region: str
    country: str
    style: str
    grape: str
    body: str
    acidity: str
    tannin: str
    sweetness: str
    oak: str
    intensity: str
    aroma_families: list[str]


class SkuList(APIModel):
    skus: list[CatalogSku]


class TastingNote(APIModel):
    id: str
    product_id: str
    product_name: str
    producer: str
    server_hook: str
    guest_description: str
    technical_note: str
    body: str
    acidity: str
    tannin: str
    sweetness: str
    oak: str
    intensity: str
    aroma_families: list[str]
    source: str
    status: str
    approved_by: str | None
    approved_at: str | None
    has_tech_sheet: bool
    created_at: str


class ServiceCardRecord(APIModel):
    id: str
    product_id: str
    product_name: str
    tasting_note_id: str
    serving_temperature: str
    glassware: str
    decanting: str
    pour_size: str
    source: str
    status: str
    approved_by: str | None
    approved_at: str | None
    created_at: str


class TastingNoteList(APIModel):
    notes: list[TastingNote]


class ServiceCardList(APIModel):
    service_cards: list[ServiceCardRecord]


class TastingDraft(APIModel):
    note: TastingNote
    service_card: ServiceCardRecord


# --- inventory, counts, storage --------------------------------------------

class StockLocation(APIModel):
    location_id: str
    location_name: str
    quantity: float
    valuation_cents: int


class StockItem(APIModel):
    sku: str
    name: str
    on_hand: float
    par: float
    low: bool
    unit: str
    depletion_30d: float
    valuation_cents: int
    currency: str
    locations: list[StockLocation]


class CellarLocation(APIModel):
    id: str
    name: str
    kind: str
    notes: str


class CellarBoard(APIModel):
    items: list[StockItem]
    locations: list[CellarLocation]


class LocationList(APIModel):
    locations: list[CellarLocation]


class LocationEnvelope(APIModel):
    location: CellarLocation


class CellarBin(APIModel):
    id: str
    location_id: str
    location_name: str
    code: str
    label: str
    qr_payload: str


class BinList(APIModel):
    bins: list[CellarBin]


class BinEnvelope(APIModel):
    bin: CellarBin


class BinLabel(APIModel):
    bin_id: str
    code: str
    label: str
    qr_payload: str
    svg: str


class StockMovementRow(APIModel):
    id: str
    sku: str
    name: str
    location_name: str
    bin_code: str
    quantity: float
    movement_type: str
    reason: str
    created_at: str


class MovementList(APIModel):
    movements: list[StockMovementRow]


class MovementEnvelope(APIModel):
    movement: StockMovementRow


class CountSessionRecord(APIModel):
    id: str
    location_id: str
    location_name: str
    status: str
    notes: str


class CountLineRecord(APIModel):
    id: str
    sku: str
    name: str
    counted_quantity: float
    expected_quantity: float | None
    device_id: str
    bin_code: str
    counted_at: str | None


class VarianceLine(APIModel):
    sku: str
    name: str
    counted_quantity: float | None
    expected_quantity: float
    variance: float | None
    variance_value_cents: int | None
    unit_cost_cents: int


class CountReading(APIModel):
    device_id: str
    counted_quantity: float
    counted_at: str | None


class CountConflict(APIModel):
    sku: str
    readings: list[CountReading]
    resolved: bool
    resolved_quantity: float | None


class CountMovement(APIModel):
    id: str
    sku: str
    quantity: float
    movement_type: str


class CountReport(APIModel):
    session: CountSessionRecord
    lines: list[CountLineRecord]
    variance_lines: list[VarianceLine]
    conflicts: list[CountConflict]
    movements: list[CountMovement] = Field(default_factory=list)


class CountSessionList(APIModel):
    sessions: list[CountSessionRecord]


class ParProposalRecord(APIModel):
    id: str
    sku: str
    name: str
    current_par: float
    proposed_par: float
    depletion_30d: float
    rationale: str
    status: str


class ParProposalList(APIModel):
    proposals: list[ParProposalRecord]


class ParProposalEnvelope(APIModel):
    proposal: ParProposalRecord


class AffectedSku(APIModel):
    sku: str
    product_name: str
    bin_code: str
    on_hand: float


class ZoneReading(APIModel):
    id: str
    zone_id: str = ""
    temp_c: float
    humidity_pct: float
    source: str = ""
    recorded_at: str | None = None
    notes: str | None = None
    in_range: bool = False


class ZoneExcursion(APIModel):
    id: str
    zone_id: str = ""
    reading_id: str = ""
    metric: str
    status: str
    measured_temp_c: float = 0
    measured_humidity_pct: float = 0
    affected_skus: list[AffectedSku]
    resolution_note: str | None = None
    created_at: str | None = None


class StorageZone(APIModel):
    id: str
    name: str
    location_id: str | None = None
    location_name: str | None = None
    target_temp_min_c: float
    target_temp_max_c: float
    target_humidity_min_pct: float
    target_humidity_max_pct: float
    notes: str | None = None
    latest_reading: ZoneReading | None = None
    status: str
    excursion: ZoneExcursion | None = None


class StorageZoneList(APIModel):
    zones: list[StorageZone]


class StorageZoneEnvelope(APIModel):
    zone: StorageZone


class ZoneReadingList(APIModel):
    readings: list[ZoneReading]


class ZoneReadingResult(APIModel):
    reading: ZoneReading
    excursion: ZoneExcursion | None
    zone: StorageZone


class ZoneExcursionList(APIModel):
    excursions: list[ZoneExcursion]


class ZoneExcursionEnvelope(APIModel):
    excursion: ZoneExcursion


# --- training, team, tonight ------------------------------------------------

class LessonStandard(APIModel):
    id: str
    slug: str
    title: str


class LessonBottle(APIModel):
    sku_id: str
    name: str


class TrainingLesson(APIModel):
    id: str
    slug: str
    title: str
    body: str
    position: str
    status: str
    can_author: bool
    quiz_id: str | None
    standards: list[LessonStandard]
    bottles: list[LessonBottle]


class TrainingLessons(APIModel):
    role: str
    name: str
    position: str | None
    can_author: bool
    lessons: list[TrainingLesson]
    drafts: list[TrainingLesson]


class TrainingOverview(APIModel):
    lessons: list[TrainingLesson]
    quiz: Any = None
    roleplay: Any = None


class QuizQuestion(APIModel):
    id: str
    prompt: str
    choices: list[str]
    kind: str = ""


class QuizReviewItem(APIModel):
    id: str
    prompt: str
    selected: int
    ok: bool
    explain: str


class TrainingQuiz(APIModel):
    id: str
    lesson_id: str | None = None
    title: str
    questions: list[QuizQuestion]
    score: int | None = None
    score_bp: int | None = None
    correct: int | None = None
    total: int | None = None
    review: list[QuizReviewItem] = Field(default_factory=list)
    next_review_at: str | None = None
    next_review_on: str | None = None


class DueReview(APIModel):
    quiz_id: str
    quiz_title: str
    question_id: str
    prompt: str
    box: int
    due_at: str
    due_on: str
    last_result: str


class DueReviewList(APIModel):
    reviews: list[DueReview]


class ServiceStandard(APIModel):
    id: str
    slug: str
    topic: str
    title: str
    body: str
    version: int
    is_default: bool
    updated_at: str


class StandardList(APIModel):
    can_author: bool
    standards: list[ServiceStandard]


class RoleplayTurn(APIModel):
    role: Literal["guest", "staff"]
    text: str
    product_ids: list[str] = Field(default_factory=list)


class RoleplayCriterion(APIModel):
    passed: bool = Field(alias="pass")
    evidence: str


class RoleplayRubric(APIModel):
    listened: RoleplayCriterion
    offered_two_options: RoleplayCriterion
    described_structure: RoleplayCriterion
    handled_price: RoleplayCriterion


class RoleplaySession(APIModel):
    id: str
    persona: str
    dish_id: str | None
    dish_name: str
    status: Literal["open", "scored"]
    transcript: list[RoleplayTurn]
    rubric: RoleplayRubric | None
    score: int | None
    started_at: str | None
    scored_at: str | None


class RoleplayResponse(APIModel):
    session: RoleplaySession


class TeamMember(APIModel):
    membership_id: str
    user_id: str
    name: str
    email: str
    role: str
    position: str | None


class TeamInvite(APIModel):
    id: str
    email: str
    role: str
    position: str | None
    invited_by_user_id: str
    created_at: str | None
    accepted_at: str | None
    revoked_at: str | None


class TeamRoster(APIModel):
    members: list[TeamMember]
    invites: list[TeamInvite]


class BriefingAckStat(APIModel):
    acked: int
    published: int
    rate_bp: int | None
    label: str


class TeamPerson(APIModel):
    user_id: str
    name: str
    email: str
    role: str
    position: str | None
    briefing_ack: BriefingAckStat
    lessons_done: int
    quiz_average_bp: int | None
    quiz_average_label: str
    roleplay_average_bp: int | None
    roleplay_average_label: str


class WeakTopic(APIModel):
    topic: str
    correct: int
    total: int
    accuracy_bp: int
    label: str


class CertificateRecord(APIModel):
    id: str
    user_id: str
    name: str
    kind: str
    label: str
    issued_on: str
    expires_on: str
    document_id: str | None
    document_filename: str
    created_by_user_id: str
    created_at: str | None
    days_left: int
    expired: bool
    expiring: bool
    due: bool
    gap_type: str
    status_label: str


class TeamWeek(APIModel):
    start: str
    end: str


class TeamProgress(APIModel):
    week: TeamWeek
    people: list[TeamPerson]
    weak_topics: list[WeakTopic]
    expiring_certificates: list[CertificateRecord]


class RemovedMember(APIModel):
    removed: bool
    user_id: str


class CertificateList(APIModel):
    certificates: list[CertificateRecord]


class CertificateEnvelope(APIModel):
    certificate: CertificateRecord


class DeletedFlag(APIModel):
    deleted: bool
    id: str


class QuizAttemptRow(APIModel):
    id: str
    user_id: str
    name: str
    staff_name: str
    score: int
    score_bp: int
    answers: list[int]
    created_at: str


class TrainingProgress(APIModel):
    attempts: list[QuizAttemptRow]


class BriefingItem(APIModel):
    title: str
    detail: str


class BriefingCard(APIModel):
    kind: str
    title: str
    body: str
    items: list[BriefingItem]


class TonightBriefing(APIModel):
    id: str
    service_date: str
    status: str
    intro: str
    cards: list[BriefingCard]
    due_review_count: int
    acknowledged: bool
    seconds_to_ack: int | None


class LowStockRow(APIModel):
    sku: str
    name: str
    on_hand: float
    par: float


class StorageAlert(APIModel):
    id: str
    zone: str
    metric: str
    status: str


class DeliveryDue(APIModel):
    po_number: str
    supplier: str
    expected_delivery_date: str | None
    status: str


class TonightApproval(APIModel):
    id: str
    kind: str
    title: str
    status: str
    href: str = ""


class PosAlert(APIModel):
    kind: str
    title: str
    href: str = ""


class CertificateGap(APIModel):
    id: str
    user_id: str
    name: str
    kind: str
    label: str
    issued_on: str
    expires_on: str
    days_left: int
    status_label: str


class SensorRecord(APIModel):
    id: str
    name: str
    zone_id: str
    zone_name: str
    location_name: str
    metric: str
    external_id: str
    sensor_key: str
    secret_last4: str
    masked: str
    last_value: str
    last_at: str | None
    stale: bool
    stale_after_hours: int
    secret: str = ""


class ReminderRecord(APIModel):
    source_type: str
    source_id: str
    rule_code: str
    title: str
    detail: str
    due_on: str
    days_left: int
    label: str
    channel: str


class TonightBoard(APIModel):
    service_date: str
    briefing_hour: int
    timezone: str
    available: bool
    role: str
    briefing: TonightBriefing | None
    low_stock: list[LowStockRow]
    storage_alerts: list[StorageAlert]
    deliveries_due: list[DeliveryDue]
    approvals: list[TonightApproval]
    pos_alerts: list[PosAlert] = Field(default_factory=list)
    sensors: list[SensorRecord] = Field(default_factory=list)
    reminders: list[ReminderRecord] = Field(default_factory=list)
    expiring_certificates: list[CertificateGap]


class TonightEnvelope(APIModel):
    role: str
    available: bool
    ready: bool
    service_date: str
    timezone: str
    briefing_hour: int
    briefing: TonightBriefing | None


class BriefingReportUser(APIModel):
    user_id: str
    name: str
    acknowledged: bool
    seconds_to_ack: int | None


class BriefingReportDay(APIModel):
    service_date: str
    briefing_id: str | None
    status: str | None
    acknowledged_count: int
    user_count: int
    users: list[BriefingReportUser]


class BriefingReport(APIModel):
    start: str
    end: str
    days: list[BriefingReportDay]


class LookupHit(APIModel):
    name: str
    producer: str
    grape: str
    region: str
    pairing: str
    server_script: str
    flavor_profile: str
    glassware: str
    serving_temperature: str
    pour_size: str
    stock: float | str
    price_cents: int
    currency: str


class LookupFilters(APIModel):
    text: str
    grape: str
    producer: str
    region: str
    dish: str
    style: str
    max_price_cents: int | None
    body: list[str]
    acidity: list[str]
    tannin: list[str]
    sweetness: list[str]
    oak: list[str]
    intensity: list[str]


class LookupResult(APIModel):
    query: str
    filters: LookupFilters
    results: list[LookupHit]


class PackItem(APIModel):
    id: str
    product_id: str
    sku: str
    name: str
    producer: str
    grape: str
    region: str
    style: str
    category: str
    body: str
    acidity: str
    tannin: str
    sweetness: str
    oak: str
    intensity: str
    on_list: bool
    price_cents: int
    currency: str
    stock: float
    eighty_six: bool


class PackNote(APIModel):
    id: str
    product_id: str
    server_hook: str
    guest_description: str
    body: str
    acidity: str
    tannin: str
    sweetness: str
    oak: str
    intensity: str


class PackCard(APIModel):
    id: str
    product_id: str
    glassware: str
    serving_temperature: str
    pour_size: str
    decanting: str


class PackDish(APIModel):
    id: str
    name: str
    description: str
    course: str


class PackPairing(APIModel):
    id: str
    sku_id: str
    dish_id: str
    dish: str
    course: str
    description: str
    script: str
    pinned: bool


class LookupPack(APIModel):
    service_date: str
    items: list[PackItem]
    notes: list[PackNote]
    cards: list[PackCard]
    dishes: list[PackDish]
    pairings: list[PackPairing]


class EightySixResult(APIModel):
    id: str
    sku: str
    name: str
    eighty_sixed_at: str | None
    eighty_sixed: bool


# --- tastings and sourcing --------------------------------------------------

class TastingSessionRow(APIModel):
    id: str
    supplier_id: str | None
    supplier: str
    title: str
    starts_at: str
    ends_at: str
    location: str
    status: str
    notes: str
    sample_count: int


class TastingSessionList(APIModel):
    sessions: list[TastingSessionRow]


class TastingDraftCard(APIModel):
    id: str
    title: str
    ics: str
    sent: bool


class TastingCreateResult(APIModel):
    draft: TastingDraftCard


class SampleDish(APIModel):
    dish_id: str
    name: str
    course: str
    score: float
    confidence: str


class SampleListPrice(APIModel):
    bottle_price: int | None
    glass_price: int | None
    bottle_label: str
    glass_label: str
    margin_pct: float | None
    margin_label: str
    cost_cents: int | None
    cost_label: str
    currency: str
    source: str
    note: str


class SamplePairs(APIModel):
    profile: str
    note: str
    dishes: list[SampleDish]


class SampleCard(APIModel):
    id: str
    session_id: str
    product_id: str | None
    product_name: str
    sku_id: str | None
    supplier_id: str | None
    supplier: str
    offer_id: str | None
    label_document_id: str | None
    matched: bool
    score: float | None
    note: str
    quoted_price_cents: int | None
    currency: str | None
    quoted_label: str
    decision: Literal["undecided", "buy", "list", "pass"]
    pass_reason: str
    purchase_order_id: str | None
    purchase_order_number: str
    purchase_order_status: str
    list_id: str | None
    list_version_id: str | None
    list_version_number: int | None
    list_price: SampleListPrice
    pairs_with: SamplePairs


class TastingSessionDetail(APIModel):
    session: TastingSessionRow
    samples: list[SampleCard]


class SampleEnvelope(APIModel):
    sample: SampleCard


class DeletedId(APIModel):
    deleted: str


class SourcingDish(APIModel):
    dish_id: str
    name: str


class SourcingBriefItem(APIModel):
    id: str
    category: str
    style: str
    price_band: str
    quantity_hint: int
    dishes: list[SourcingDish]
    sample_id: str | None
    offer_id: str | None
    rationale: str
    position: int


class SourcingBrief(APIModel):
    id: str
    list_id: str | None
    title: str
    status: str
    items: list[SourcingBriefItem]


class SourcingBriefList(APIModel):
    briefs: list[SourcingBrief]


class SourcingBriefEnvelope(APIModel):
    brief: SourcingBrief


class RepFollowup(APIModel):
    id: str
    session_id: str
    supplier_id: str | None
    supplier: str
    to_email: str
    subject: str
    body: str
    purchase_order_id: str | None
    purchase_order_number: str
    mailto: str
    sent: bool


class RepFollowupEnvelope(APIModel):
    followup: RepFollowup | None


class RepFollowupDraft(APIModel):
    followup: RepFollowup


class TastingHistoryRow(APIModel):
    supplier_id: str
    supplier: str
    product_id: str
    product: str
    tasted: int
    buy: int
    listed: int = Field(alias="list")
    passed: int = Field(alias="pass")
    undecided: int
    bought_bottles: int
    invoiced_bottles: int
    last_cost_cents: int | None
    last_cost_label: str


class TastingHistory(APIModel):
    rows: list[TastingHistoryRow]


class InviteSlot(APIModel):
    position: int = 0
    starts_at: str
    ends_at: str
    source: str = ""
    chosen: bool = False


class InviteGapDish(APIModel):
    name: str


class InviteGap(APIModel):
    category: str
    style: str
    price_band: str
    quantity_hint: int
    dishes: list[InviteGapDish]


class InviteSampleRef(APIModel):
    sample_id: str
    name: str


class InviteFacts(APIModel):
    source: str
    gaps: list[InviteGap]
    samples: list[InviteSampleRef]


class InviteApproval(APIModel):
    id: str = ""
    decision: str = ""
    required_role: str = ""
    comment: str | None = None
    decided_at: str | None = None


class InviteAttendee(APIModel):
    kind: str
    name: str
    email: str
    user_id: str | None = None


class TastingInvite(APIModel):
    id: str
    session_id: str
    title: str
    supplier: str
    status: str
    agenda_note: str
    agenda_facts: InviteFacts
    slots: list[InviteSlot]
    attendees: list[InviteAttendee]
    approval: InviteApproval | None
    chosen_starts_at: str
    email_subject: str
    email_body: str
    email_mailto: str
    sent: bool
    driver: str
    ics_ready: bool


class InviteStaff(APIModel):
    id: str
    name: str
    email: str
    role: str


class InviteRep(APIModel):
    supplier: str
    name: str
    email: str


class InviteDesk(APIModel):
    suggestions: list[InviteSlot]
    staff: list[InviteStaff]
    rep: InviteRep
    can_decide: bool
    invite: TastingInvite | None


# --- suppliers, purchasing, offers ------------------------------------------

class SupplierContactRow(APIModel):
    id: str
    supplier_id: str
    name: str
    role: str | None
    email: str
    phone: str | None
    is_primary: bool


class SupplierRow(APIModel):
    id: str
    name: str
    kind: str
    contact_email: str
    account_number: str | None
    order_minimum_cents: int
    default_case_size: int
    delivery_days: list[str]
    lead_time_days: int
    payment_terms: str | None
    notes: str
    contacts: list[SupplierContactRow]


class SupplierList(APIModel):
    suppliers: list[SupplierRow]


class SupplierEnvelope(APIModel):
    supplier: SupplierRow


class ContactEnvelope(APIModel):
    contact: SupplierContactRow
    supplier: SupplierRow


class PurchaseLine(APIModel):
    id: str
    sku: str
    name: str
    product_name: str
    case_size: int
    cases_ordered: int
    quantity_ordered: int
    quantity_received: int
    unit_cost_cents: int
    line_total_cents: int
    vintage: str | None


class PurchaseApproval(APIModel):
    id: str
    decision: str
    required_role: str
    comment: str | None
    decided_at: str | None


class PurchaseOrderRow(APIModel):
    id: str
    po_number: str | None
    status: str
    supplier_id: str
    supplier: str
    contact: SupplierContactRow | None
    expected_delivery_date: str | None
    subtotal_cents: int
    order_minimum_cents: int
    minimum_met: bool
    shortfall_cents: int
    pdf_document_id: str | None
    sent_via: str | None
    lines: list[PurchaseLine]
    approval: PurchaseApproval


class PurchaseOrderList(APIModel):
    orders: list[PurchaseOrderRow]


class SupplierName(APIModel):
    id: str
    name: str
    kind: str = ""
    contact_email: str | None = None
    notes: str = ""


class SupplierNameList(APIModel):
    suppliers: list[SupplierName]


class SupplierProfile(APIModel):
    id: str
    name: str
    kind: str
    rep_name: str
    rep_email: str
    rep_phone: str | None
    delivery_days: list[str]
    order_minimum_cents: int
    order_minimum_currency: str
    order_minimum_label: str
    payment_terms: str | None
    notes: str
    lead_time_days: int
    default_case_size: int


class ProfileEnvelope(APIModel):
    supplier: SupplierProfile


class CatalogChoice(APIModel):
    product_id: str
    sku_id: str
    name: str
    producer: str
    barcode: str


class AllocationRecord(APIModel):
    id: str
    supplier_id: str
    product_id: str
    product_name: str
    quantity: int
    period_label: str
    period_start: str | None
    period_end: str | None


class AllocationEnvelope(APIModel):
    allocation: AllocationRecord


class OfferRecord(APIModel):
    id: str
    supplier_id: str
    supplier: str
    product_id: str
    product_name: str
    sku_id: str | None
    sku: str
    unit: str
    case_size: int
    price_cents: int
    price_label: str
    currency: str
    valid_from: str
    valid_to: str | None
    source: str
    source_document_id: str | None
    price_sheet_id: str | None


class OfferList(APIModel):
    offers: list[OfferRecord]


class OfferEnvelope(APIModel):
    offer: OfferRecord


class PriceSheetLine(APIModel):
    line: int
    name: str
    producer: str
    sku: str
    unit: str
    case_size: int
    price_cents: int
    price_label: str
    currency: str
    valid_from: str
    valid_to: str | None
    product_id: str | None
    sku_id: str | None
    product_name: str
    status: str
    message: str


class PriceSheetRecord(APIModel):
    id: str
    supplier_id: str
    supplier: str
    document_id: str
    status: str
    rows: list[PriceSheetLine]
    matched: int
    unmatched: int
    created_at: str | None
    reviewed_at: str | None


class PriceSheetEnvelope(APIModel):
    price_sheet: PriceSheetRecord


class PriceSheetApplied(APIModel):
    price_sheet: PriceSheetRecord
    offers: list[OfferRecord]


class SupplierDeskPayload(APIModel):
    supplier: SupplierProfile
    allocations: list[AllocationRecord]
    offers: list[OfferRecord]
    current_offers: list[OfferRecord]
    price_sheets: list[PriceSheetRecord]
    products: list[CatalogChoice]


class PriceProduct(APIModel):
    id: str
    name: str
    producer: str


class PricePointRecord(APIModel):
    date: str
    kind: str
    price_cents: int
    price_label: str
    currency: str
    supplier_id: str
    supplier: str
    source: str
    offer_id: str | None
    invoice_id: str | None


class PriceHistory(APIModel):
    product: PriceProduct
    points: list[PricePointRecord]


class InvoiceLine(APIModel):
    sku: str
    product_name: str = ""
    quantity: float
    unit_cost_cents: int
    vintage: str | None = None
    po_line_id: str | None = None


class InvoiceRecord(APIModel):
    id: str
    purchase_order_id: str | None
    invoice_number: str
    invoice_date: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    document_id: str
    filename: str
    sha256: str
    content_type: str
    extracted_lines: list[InvoiceLine]
    extraction_mode: str
    status: str


class InvoiceList(APIModel):
    invoices: list[InvoiceRecord]


class DiscrepancyLine(APIModel):
    sku: str
    flags: list[str]
    cost_delta_cents: int


class DiscrepancySummary(APIModel):
    has_discrepancies: bool
    counts: dict[str, int]
    cost_delta_cents: int
    lines: list[DiscrepancyLine]


class ReceiptLineRecord(APIModel):
    id: str
    po_line_id: str | None
    sku: str
    product_name: str
    ordered_qty: float
    invoiced_qty: float | None
    counted_qty: float
    ordered_unit_cost_cents: int
    invoiced_unit_cost_cents: int | None
    ordered_vintage: str | None
    received_vintage: str | None
    bin_id: str | None
    flags: list[str]
    resolution_note: str | None
    cost_delta_cents: int


class ReceiptRecord(APIModel):
    id: str
    purchase_order_id: str
    po_number: str | None
    supplier: str
    purchase_order_status: str | None
    invoice_id: str | None
    status: str
    discrepancy_summary: DiscrepancySummary
    notes: str | None
    lines: list[ReceiptLineRecord]
    a2ui_operations: list[Any] = Field(default_factory=list)


class ReceiptList(APIModel):
    receipts: list[ReceiptRecord]


# --- pos, sensors, reminders, compliance, usage ----------------------------

class PosLocation(APIModel):
    location_id: str
    name: str


class PosStatus(APIModel):
    connected: bool
    provider: str
    status: str
    location_id: str
    location_name: str
    key_last4: str
    masked: str
    last_synced_at: str | None
    watermark: str
    demo_mode: bool
    locations: list[PosLocation] = Field(default_factory=list)


class PosCatalogItem(APIModel):
    item_id: str
    variation_id: str
    name: str
    variation_name: str
    sku_hint: str


class PosCatalog(APIModel):
    items: list[PosCatalogItem]


class PosMapping(APIModel):
    id: str
    provider: str
    item_id: str
    variation_id: str
    sku_id: str
    sku: str
    pour_ml: float | None
    units_per_sale: float


class PosMappingList(APIModel):
    mappings: list[PosMapping]


class PosMappingEnvelope(APIModel):
    mapping: PosMapping


class RemovedId(APIModel):
    removed: str


class PosRun(APIModel):
    id: str
    status: str
    started_at: str | None
    finished_at: str | None
    posted: int
    skipped: int
    unmapped_count: int
    error: str


class PosRunList(APIModel):
    runs: list[PosRun]


class PosGapItem(APIModel):
    variation_id: str
    item_id: str
    name: str
    quantity: str


class PosGapList(APIModel):
    items: list[PosGapItem]


class PosSyncResult(APIModel):
    posted: int
    skipped: int
    unmapped: list[PosGapItem]


class SensorList(APIModel):
    sensors: list[SensorRecord]
    stale_after_hours: int


class SensorImportRow(APIModel):
    line: int
    sensor: str
    external_id: str
    at: str
    metric: str
    value: str
    zone: str
    excursion: str
    duplicate: bool
    error: str


class SensorImport(APIModel):
    id: str
    filename: str
    status: str
    rows: list[SensorImportRow]
    posted: int = 0
    skipped: int = 0
    excursions: int = 0


class SensorImportList(APIModel):
    imports: list[SensorImport]


class WebhookReading(APIModel):
    status: str
    reading_id: str = ""
    excursion: bool = False


class WebhookResult(APIModel):
    accepted: int
    duplicates: int
    readings: list[WebhookReading] = Field(default_factory=list)


class ReminderRule(APIModel):
    code: str
    title: str
    detail: str
    lead_days: int = 0
    applies_to: str = ""
    jurisdiction: str = ""


class ReminderList(APIModel):
    jurisdiction: str
    rules: list[ReminderRule]
    reminders: list[ReminderRecord]
    channel: str


class LicenseRecorded(APIModel):
    id: str
    label: str
    expires_on: str
    rule_code: str = ""
    document_id: str | None = None


class ReminderDecision(APIModel):
    status: str
    channel: str


class AuditEventRow(APIModel):
    id: str
    seq: int
    actor_email: str
    action: str
    entity_type: str
    entity_id: str | None
    before_json: dict[str, Any] | None
    after_json: dict[str, Any] | None
    prev_hash: str
    event_hash: str
    created_at: str
    summary: str


class AuditChain(APIModel):
    valid: bool
    checked_count: int
    head_hash: str | None
    broken_event_id: str | None
    reason: str | None


class AuditEventList(APIModel):
    events: list[AuditEventRow]
    chain: AuditChain


class VaultDocument(APIModel):
    id: str
    doc_type: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    linked_entity_type: str
    linked_entity_id: str | None
    uploaded_by_user_id: str | None
    created_at: str


class DocumentList(APIModel):
    documents: list[VaultDocument]


class DocumentEnvelope(APIModel):
    document: VaultDocument


class RetentionPolicy(APIModel):
    document_retention_years: int
    can_edit: bool


class AuditPackPurchase(APIModel):
    supplier: str
    po_count: int
    invoice_count: int
    total_invoiced_cents: int
    total_received_value_cents: int


class AuditPackInvoice(APIModel):
    invoice_number: str
    total_cents: int
    status: str


class AuditPackGap(APIModel):
    purchase_order_id: str
    po_number: str
    supplier: str
    status: str
    reason: str


class AuditVenue(APIModel):
    id: str
    name: str


class AuditValuation(APIModel):
    start_bottles: float
    start_value_cents: int
    end_bottles: float
    end_value_cents: int


class AuditVariance(APIModel):
    quantity_delta: float
    cost_impact_cents: int
    count_sessions: list[Any]


class AuditWaste(APIModel):
    cost_impact_cents: int
    movements: list[Any]


class AuditRetention(APIModel):
    document_retention_years: int
    retain_until: str


class AuditPackChain(APIModel):
    valid: bool
    checked: int
    head_hash: str | None


class AuditPackPreview(APIModel):
    venue: AuditVenue
    start_date: str
    end_date: str
    purchases_by_supplier: list[AuditPackPurchase]
    invoice_register: list[AuditPackInvoice]
    missing_invoice_gaps: list[AuditPackGap]
    inventory_valuation: AuditValuation
    variance_and_shrinkage: AuditVariance
    comp_breakage_waste: AuditWaste
    retention: AuditRetention
    chain: AuditPackChain


class ComplianceGaps(APIModel):
    missing_invoice_gaps: list[Any]
    open_excursions: list[Any]
    certificate_gaps: list[Any]
    pos_gaps: list[Any]
    reminders: list[Any]
    chain: AuditPackChain


class AuditorColumn(APIModel):
    key: str
    label: str
    type: Literal["text", "number", "money", "date"]


class AuditorLink(APIModel):
    label: str
    href: str


class AuditorRow(APIModel):
    id: str
    cells: dict[str, str | int]
    links: list[AuditorLink]


class AuditorPage(APIModel):
    limit: int
    offset: int
    total: int


class AuditorTable(APIModel):
    title: str
    columns: list[AuditorColumn]
    rows: list[AuditorRow]
    totals: dict[str, str | int]
    page: AuditorPage


class AuditorQuery(APIModel):
    audit_table: AuditorTable


class UsageByAgent(APIModel):
    subagent: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_micro_usd: int


class UsageByDay(APIModel):
    day: str
    calls: int
    cost_micro_usd: int


class UsageReport(APIModel):
    month: str
    monthly_spend_cap_cents: int | None
    spent_cents: int
    spent_micro_usd: int
    requests_per_minute: int | None
    requests_this_minute: int
    by_subagent: list[UsageByAgent]
    by_day: list[UsageByDay]
    cap_status: str
    can_edit: bool
    demo: bool


# Mounted by ``mount_agui`` at process startup, not at import. ``make types``
# and the test suite must agree whether these paths exist.
STARTUP_AGUI_PATHS = {"/ag-ui", "/ag-ui/health"}

# File, calendar, and redirect routes stay on the schema FastAPI already emits.
UNMODELED_ROUTES = {
    ("get", "/auth/google"),
    ("get", "/auth/callback"),
    ("get", "/lists/versions/{version_id}/pdf"),
    ("get", "/lists/versions/{version_id}/qr.png"),
    ("get", "/procurement/orders/{po_id}/pdf"),
    ("get", "/procurement/invoices/{invoice_id}/document"),
    ("get", "/compliance/documents/{document_id}/download"),
    ("get", "/compliance/audit-pack/export"),
    ("get", "/tastings/{session_id}.ics"),
    ("get", "/tastings/{session_id}/invite.ics"),
}


def _routes() -> dict[tuple[str, str], type[APIModel]]:
    pairing = PairingGridResult
    review = MenuIngestResult
    detail = BeverageListDetail
    version = ListVersionRecord
    order = PurchaseOrderRow
    receipt = ReceiptRecord
    sample = SampleEnvelope
    invite = InviteDesk
    brief = SourcingBriefEnvelope
    roleplay = RoleplayResponse
    settings = LlmSettings
    usage = UsageReport
    pos = PosStatus
    query = AuditorQuery
    note = TastingNote
    card = ServiceCardRecord
    lesson = TrainingLesson
    standard = ServiceStandard
    quiz = TrainingQuiz
    certificate = CertificateRecord
    sensor_import = SensorImport
    sheet = PriceSheetEnvelope
    return {
        ("get", "/auth/config"): AuthConfig,
        ("get", "/auth/me"): AccountEnvelope,
        ("get", "/auth/csrf"): OkResponse,
        ("get", "/auth/demo-personas"): DemoPersonaList,
        ("post", "/auth/demo-persona"): DemoPersona,
        ("post", "/auth/logout"): OkResponse,
        ("get", "/health"): HealthPayload,
        ("get", "/status"): StatusPayload,
        ("get", "/fixtures/sample-menu"): SampleMenu,
        ("get", "/settings/llm"): settings,
        ("post", "/settings/llm"): settings,
        ("delete", "/settings/llm"): settings,
        ("get", "/ag-ui/threads/{thread_id}/messages"): AguiMessages,
        ("post", "/menus/ingest"): review,
        ("post", "/menus/upload"): review,
        ("post", "/menus/parse"): MenuParseResult,
        ("get", "/menus"): MenuList,
        ("get", "/menus/{menu_id}"): MenuDetail,
        ("patch", "/menus/{menu_id}/versions/{version_id}/dishes/{dish_id}"): review,
        ("post", "/menus/{menu_id}/versions/{version_id}/confirm"): review,
        ("get", "/menus/{menu_id}/pairings"): pairing,
        ("post", "/menus/{menu_id}/pair"): pairing,
        ("post", "/menus/{menu_id}/pairings/{pairing_id}/pin"): pairing,
        ("post", "/menus/{menu_id}/pairings/{pairing_id}/reject"): pairing,
        ("post", "/menus/{menu_id}/pairings/{pairing_id}/swap"): pairing,
        ("get", "/lists/pricing-rules"): PricingRulesResponse,
        ("put", "/lists/pricing-rules"): PricingRulesResponse,
        ("post", "/lists/curate"): detail,
        ("get", "/lists"): ListIndex,
        ("get", "/lists/{list_id}/coverage"): ListCoverage,
        ("get", "/lists/{list_id}/health"): ListHealth,
        ("post", "/lists/{list_id}/items"): detail,
        ("patch", "/lists/{list_id}/items/{item_id}"): detail,
        ("delete", "/lists/{list_id}/items/{item_id}"): detail,
        ("put", "/lists/{list_id}/sections"): detail,
        ("post", "/lists/import"): ListImportResult,
        ("post", "/lists/{list_id}/versions"): version,
        ("get", "/lists/{list_id}/versions"): ListVersionIndex,
        ("get", "/lists/versions/{version_id}"): version,
        ("get", "/lists/versions/{version_id}/diff"): ListDiff,
        ("post", "/lists/versions/{version_id}/submit"): version,
        ("post", "/lists/versions/{version_id}/approve"): version,
        ("post", "/lists/versions/{version_id}/reject"): version,
        ("post", "/lists/versions/{version_id}/revoke-public"): version,
        ("get", "/public/lists/{token}"): PublicList,
        ("get", "/products"): ProductList,
        ("get", "/products/{product_id}"): CatalogProduct,
        ("get", "/skus"): SkuList,
        ("get", "/skus/{sku_id}"): CatalogSku,
        ("get", "/products/{product_id}/notes"): TastingNoteList,
        ("post", "/products/{product_id}/notes"): TastingDraft,
        ("get", "/products/{product_id}/notes/{note_id}"): note,
        ("patch", "/products/{product_id}/notes/{note_id}"): note,
        ("post", "/products/{product_id}/notes/draft"): TastingDraft,
        ("post", "/products/{product_id}/notes/{note_id}/approve"): note,
        ("get", "/products/{product_id}/service-cards"): ServiceCardList,
        ("get", "/products/{product_id}/service-cards/{card_id}"): card,
        ("patch", "/products/{product_id}/service-cards/{card_id}"): card,
        ("post", "/products/{product_id}/service-cards/{card_id}/approve"): card,
        ("get", "/inventory"): CellarBoard,
        ("patch", "/inventory/{sku}"): CellarBoard,
        ("get", "/inventory/locations"): LocationList,
        ("post", "/inventory/locations"): LocationEnvelope,
        ("get", "/inventory/bins"): BinList,
        ("post", "/inventory/bins"): BinEnvelope,
        ("get", "/inventory/bins/{bin_id}/qr"): BinLabel,
        ("get", "/inventory/movements"): MovementList,
        ("post", "/inventory/movements"): MovementEnvelope,
        ("post", "/inventory/transfers"): MovementList,
        ("get", "/inventory/storage-zones"): StorageZoneList,
        ("post", "/inventory/storage-zones"): StorageZoneEnvelope,
        ("get", "/inventory/storage-zones/{zone_id}/readings"): ZoneReadingList,
        ("post", "/inventory/storage-zones/{zone_id}/readings"): ZoneReadingResult,
        ("get", "/inventory/excursions"): ZoneExcursionList,
        ("post", "/inventory/excursions/{excursion_id}/acknowledge"): ZoneExcursionEnvelope,
        ("get", "/inventory/counts"): CountSessionList,
        ("post", "/inventory/counts"): CountSessionRecord,
        ("get", "/inventory/counts/{session_id}"): CountReport,
        ("post", "/inventory/counts/{session_id}/sync"): CountReport,
        ("post", "/inventory/counts/{session_id}/submit"): CountReport,
        ("post", "/inventory/counts/{session_id}/conflicts/{sku}/resolve"): CountReport,
        ("post", "/inventory/counts/{session_id}/approve"): CountReport,
        ("get", "/inventory/par-proposals"): ParProposalList,
        ("post", "/inventory/par-proposals/generate"): ParProposalList,
        ("post", "/inventory/par-proposals/{proposal_id}/accept"): ParProposalEnvelope,
        ("post", "/inventory/par-proposals/{proposal_id}/reject"): ParProposalEnvelope,
        ("get", "/training"): TrainingOverview,
        ("get", "/training/lessons"): TrainingLessons,
        ("post", "/training/lessons/draft"): lesson,
        ("post", "/training/lessons/{lesson_id}/approve"): lesson,
        ("patch", "/training/lessons/{lesson_id}"): lesson,
        ("get", "/training/standards"): StandardList,
        ("put", "/training/standards"): standard,
        ("post", "/training/standards/{slug}/reset"): standard,
        ("post", "/training/quizzes/from-list"): quiz,
        ("get", "/training/quizzes/{quiz_id}"): quiz,
        ("post", "/training/quizzes/{quiz_id}/attempts"): quiz,
        ("get", "/training/reviews/due"): DueReviewList,
        ("post", "/training/roleplay"): roleplay,
        ("post", "/training/roleplay/{session_id}/reply"): roleplay,
        ("post", "/training/roleplay/{session_id}/score"): roleplay,
        ("get", "/training/certificates"): CertificateList,
        ("get", "/training/certificates/{certificate_id}"): certificate,
        ("get", "/training/progress"): TrainingProgress,
        ("get", "/team"): TeamRoster,
        ("get", "/team/progress"): TeamProgress,
        ("post", "/team/invites"): TeamInvite,
        ("post", "/team/invites/{invite_id}/revoke"): TeamInvite,
        ("patch", "/team/members/{user_id}"): TeamMember,
        ("delete", "/team/members/{user_id}"): RemovedMember,
        ("get", "/team/certificates"): CertificateList,
        ("post", "/team/certificates"): CertificateEnvelope,
        ("get", "/team/certificates/{certificate_id}"): certificate,
        ("patch", "/team/certificates/{certificate_id}"): CertificateEnvelope,
        ("delete", "/team/certificates/{certificate_id}"): DeletedFlag,
        ("post", "/team/certificates/{certificate_id}/document"): CertificateEnvelope,
        ("get", "/tonight"): TonightBoard,
        ("get", "/tonight/briefing"): TonightEnvelope,
        ("post", "/tonight/briefing/rebuild"): TonightEnvelope,
        ("post", "/tonight/briefing/publish"): TonightEnvelope,
        ("get", "/tonight/briefing/report"): BriefingReport,
        ("post", "/tonight/briefing/{briefing_id}/ack"): TonightBriefing,
        ("get", "/lookup"): LookupResult,
        ("get", "/lookup/pack"): LookupPack,
        ("post", "/cellar/skus/{sku_id}/86"): EightySixResult,
        ("delete", "/cellar/skus/{sku_id}/86"): EightySixResult,
        ("get", "/suppliers"): SupplierNameList,
        ("get", "/tastings"): TastingSessionList,
        ("post", "/tastings"): TastingCreateResult,
        ("get", "/tastings/{session_id}"): TastingSessionDetail,
        ("patch", "/tastings/{session_id}"): TastingSessionDetail,
        ("delete", "/tastings/{session_id}"): DeletedId,
        ("post", "/tastings/{session_id}/samples"): sample,
        ("post", "/tastings/{session_id}/samples/label"): sample,
        ("post", "/tastings/{session_id}/samples/{sample_id}/label"): sample,
        ("patch", "/tastings/{session_id}/samples/{sample_id}"): sample,
        ("delete", "/tastings/{session_id}/samples/{sample_id}"): DeletedId,
        ("post", "/tastings/{session_id}/samples/{sample_id}/score"): sample,
        ("post", "/tastings/{session_id}/samples/{sample_id}/decision"): sample,
        ("get", "/tastings/{session_id}/follow-up"): RepFollowupEnvelope,
        ("post", "/tastings/{session_id}/follow-up"): RepFollowupDraft,
        ("get", "/tastings/{session_id}/invite"): invite,
        ("post", "/tastings/{session_id}/invite"): invite,
        ("post", "/tastings/{session_id}/invite/approve"): invite,
        ("post", "/tastings/{session_id}/invite/reject"): invite,
        ("get", "/sourcing/briefs"): SourcingBriefList,
        ("post", "/sourcing/briefs"): brief,
        ("get", "/sourcing/briefs/{brief_id}"): brief,
        ("patch", "/sourcing/items/{item_id}"): brief,
        ("get", "/sourcing/history"): TastingHistory,
        ("get", "/procurement/suppliers"): SupplierList,
        ("post", "/procurement/suppliers"): SupplierEnvelope,
        ("post", "/procurement/suppliers/{supplier_id}/contacts"): ContactEnvelope,
        ("get", "/procurement/orders"): PurchaseOrderList,
        ("post", "/procurement/orders"): order,
        ("post", "/procurement/orders/draft-from-reorder"): PurchaseOrderList,
        ("get", "/procurement/orders/{po_id}"): order,
        ("post", "/procurement/orders/{po_id}/approve"): order,
        ("post", "/procurement/orders/{po_id}/reject"): order,
        ("post", "/procurement/orders/{po_id}/send"): order,
        ("post", "/procurement/orders/{po_id}/close"): order,
        ("post", "/procurement/orders/{po_id}/cancel"): order,
        ("post", "/procurement/orders/{po_id}/invoices"): InvoiceRecord,
        ("get", "/procurement/invoices"): InvoiceList,
        ("get", "/procurement/invoices/{invoice_id}"): InvoiceRecord,
        ("post", "/procurement/orders/{po_id}/receipts"): receipt,
        ("get", "/procurement/receipts"): ReceiptList,
        ("get", "/procurement/receipts/{receipt_id}"): receipt,
        ("post", "/procurement/receipts/{receipt_id}/accept"): receipt,
        ("post", "/purchase-orders/draft"): PurchaseOrderList,
        ("get", "/purchase-orders"): PurchaseOrderList,
        ("get", "/procurement/suppliers/{supplier_id}/desk"): SupplierDeskPayload,
        ("patch", "/procurement/suppliers/{supplier_id}/profile"): ProfileEnvelope,
        ("post", "/procurement/suppliers/{supplier_id}/allocations"): AllocationEnvelope,
        ("patch", "/procurement/allocations/{allocation_id}"): AllocationEnvelope,
        ("delete", "/procurement/allocations/{allocation_id}"): DeletedId,
        ("get", "/procurement/offers"): OfferList,
        ("post", "/procurement/offers"): OfferEnvelope,
        ("patch", "/procurement/offers/{offer_id}"): OfferEnvelope,
        ("delete", "/procurement/offers/{offer_id}"): DeletedId,
        ("get", "/procurement/products/{product_id}/price-history"): PriceHistory,
        ("post", "/procurement/price-sheets"): sheet,
        ("get", "/procurement/price-sheets/{sheet_id}"): sheet,
        ("post", "/procurement/price-sheets/{sheet_id}/apply"): PriceSheetApplied,
        ("post", "/procurement/price-sheets/{sheet_id}/reject"): PriceSheetApplied,
        ("get", "/pos/status"): pos,
        ("get", "/pos/catalog"): PosCatalog,
        ("get", "/pos/mappings"): PosMappingList,
        ("post", "/pos/mappings"): PosMappingEnvelope,
        ("delete", "/pos/mappings/{mapping_id}"): RemovedId,
        ("get", "/pos/runs"): PosRunList,
        ("get", "/pos/gaps"): PosGapList,
        ("post", "/pos/connect/demo"): pos,
        ("post", "/pos/connect/square"): pos,
        ("post", "/pos/location"): pos,
        ("post", "/pos/sync"): PosSyncResult,
        ("get", "/sensors"): SensorList,
        ("post", "/sensors"): SensorRecord,
        ("post", "/sensors/{sensor_id}/rotate"): SensorRecord,
        ("get", "/sensors/imports"): SensorImportList,
        ("post", "/sensors/imports"): sensor_import,
        ("post", "/sensors/imports/{import_id}/apply"): sensor_import,
        ("post", "/sensors/imports/{import_id}/reject"): sensor_import,
        ("post", "/sensors/webhook/{sensor_key}"): WebhookResult,
        ("get", "/reminders"): ReminderList,
        ("post", "/licenses"): LicenseRecorded,
        ("post", "/reminders/decide"): ReminderDecision,
        ("get", "/compliance/audit-events"): AuditEventList,
        ("get", "/compliance/audit-events/verify"): AuditChain,
        ("get", "/compliance/documents"): DocumentList,
        ("post", "/compliance/documents"): DocumentEnvelope,
        ("get", "/compliance/retention"): RetentionPolicy,
        ("patch", "/compliance/retention"): RetentionPolicy,
        ("get", "/compliance/audit-pack/preview"): AuditPackPreview,
        ("get", "/compliance/gaps"): ComplianceGaps,
        ("get", "/compliance/queries/stock"): query,
        ("get", "/compliance/queries/conditions"): query,
        ("get", "/compliance/queries/compliance"): query,
        ("get", "/compliance/queries/pos"): query,
        ("get", "/compliance/queries/lists"): query,
        ("get", "/compliance/queries/purchases"): query,
        ("get", "/compliance/queries/events"): query,
        ("get", "/usage"): usage,
        ("put", "/usage/limits"): usage,
    }


RESPONSE_MODELS = _routes()
