from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _as_id(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    return value


Id = Annotated[str, BeforeValidator(_as_id)]

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class FloorA2uiBinding(BaseModel):
    path: str


class FloorA2uiComponent(BaseModel):
    id: str
    component: str
    children: list[str] | None = None
    text: FloorA2uiBinding | None = None
    variant: str | None = None
    lessons: FloorA2uiBinding | None = None
    quiz: FloorA2uiBinding | None = None
    briefing: FloorA2uiBinding | None = None
    lookup: FloorA2uiBinding | None = None
    session: FloorA2uiBinding | None = None
    events: FloorA2uiBinding | None = None
    chain: FloorA2uiBinding | None = None


class FloorA2uiCreateSurface(BaseModel):
    surfaceId: str
    catalogId: str


class FloorA2uiUpdateComponents(BaseModel):
    surfaceId: str
    components: list[FloorA2uiComponent]


class FloorA2uiUpdateData(BaseModel):
    surfaceId: str
    path: str
    value: Any


class FloorA2uiOperation(BaseModel):
    version: str
    createSurface: FloorA2uiCreateSurface | None = None
    updateComponents: FloorA2uiUpdateComponents | None = None
    updateDataModel: FloorA2uiUpdateData | None = None


class QuizQuestion(BaseModel):
    id: str
    prompt: str
    choices: list[str]
    kind: str | None = None


class QuizReviewItem(BaseModel):
    id: str
    prompt: str
    selected: int
    ok: bool
    explain: str


class TrainingQuiz(BaseModel):
    id: Id
    lesson_id: Id | None
    title: str
    status: str
    source: str
    questions: list[QuizQuestion]
    score: float | None = None
    score_bp: int | None = None
    correct: int | None = None
    total: int | None = None
    review: list[QuizReviewItem] | None = None
    next_review_at: datetime | None = None
    next_review_on: date | None = None
    user_id: Id | None = None
    name: str | None = None


class CitedStandard(BaseModel):
    id: Id
    slug: str
    title: str


class LessonBottle(BaseModel):
    sku_id: Id
    name: str


class TrainingLesson(BaseModel):
    id: Id
    slug: str
    title: str
    body: str
    position: str
    role: str
    category: str
    status: str
    source: str
    standard_ids: list[str]
    sku_ids: list[str]
    standards: list[CitedStandard]
    bottles: list[LessonBottle]
    quiz_id: Id | None
    can_author: bool
    created_at: datetime
    approved_at: datetime | None
    quiz: TrainingQuiz | None = None


class TrainingLessons(BaseModel):
    role: str
    name: str
    position: str | None
    can_author: bool
    lessons: list[TrainingLesson]
    drafts: list[TrainingLesson]


class DueReview(BaseModel):
    quiz_id: Id
    quiz_title: str
    question_id: str
    prompt: str
    box: int
    due_at: datetime
    due_on: date
    last_result: str


class DueReviews(BaseModel):
    reviews: list[DueReview]


class ServiceStandard(BaseModel):
    id: Id
    slug: str
    topic: str
    title: str
    body: str
    version: int
    is_default: bool
    updated_at: datetime


class ServiceStandardList(BaseModel):
    can_author: bool
    standards: list[ServiceStandard]


class RoleplayTurn(BaseModel):
    role: Literal["guest", "staff"]
    text: str
    product_ids: list[str]


class RoleplayCriterion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    passed: bool = Field(alias="pass")
    evidence: str


class RoleplayRubric(BaseModel):
    listened: RoleplayCriterion
    offered_two_options: RoleplayCriterion
    described_structure: RoleplayCriterion
    handled_price: RoleplayCriterion


class RoleplaySession(BaseModel):
    id: str
    persona: str
    dish_id: str | None
    dish_name: str
    status: Literal["open", "scored"]
    transcript: list[RoleplayTurn]
    rubric: RoleplayRubric | None
    score: int | None
    started_at: datetime
    scored_at: datetime | None


class RoleplayResponse(BaseModel):
    session: RoleplaySession
    a2ui_operations: list[FloorA2uiOperation]


class TeamMember(BaseModel):
    membership_id: str
    user_id: str
    name: str
    email: str
    role: str
    position: str | None


class TeamInvite(BaseModel):
    id: str
    email: str
    role: str
    position: str | None
    invited_by_user_id: str
    created_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class TeamRoster(BaseModel):
    members: list[TeamMember]
    invites: list[TeamInvite]


class BriefingAckRate(BaseModel):
    acked: int
    published: int
    rate_bp: int | None
    label: str


class TeamWeek(BaseModel):
    start: date
    end: date


class TeamPerson(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    position: str | None
    briefing_ack: BriefingAckRate
    lessons_done: int
    quiz_average_bp: int | None
    quiz_average_label: str
    roleplay_average_bp: int | None
    roleplay_average_label: str


class WeakTopic(BaseModel):
    topic: str
    correct: int
    total: int
    accuracy_bp: int
    label: str


class CertificateRecord(BaseModel):
    id: str
    user_id: str
    name: str
    kind: str
    label: str
    issued_on: date
    expires_on: date
    document_id: str | None
    document_filename: str
    created_by_user_id: str
    created_at: datetime
    days_left: int
    expired: bool
    expiring: bool
    due: bool
    gap_type: str
    status_label: str


class CertificateGap(BaseModel):
    gap_type: str
    id: str
    user_id: str
    name: str
    kind: str
    label: str
    issued_on: date
    expires_on: date
    days_left: int
    status_label: str


class TeamProgress(BaseModel):
    week: TeamWeek
    people: list[TeamPerson]
    weak_topics: list[WeakTopic]
    expiring_certificates: list[CertificateGap]


class CertificateList(BaseModel):
    certificates: list[CertificateRecord]


class CertificateEnvelope(BaseModel):
    certificate: CertificateRecord


class DeletedCertificate(BaseModel):
    deleted: bool
    id: str


class RemovedMember(BaseModel):
    removed: bool
    user_id: str


class BriefingItem(BaseModel):
    title: str
    detail: str


class BriefingCard(BaseModel):
    kind: str
    title: str
    body: str
    items: list[BriefingItem]


class TonightBriefing(BaseModel):
    id: str
    service_date: date
    status: str
    intro: str
    cards: list[BriefingCard]
    due_review_count: int
    published_at: datetime | None
    acknowledged: bool
    seconds_to_ack: int | None
    timezone: str
    briefing_hour: int


class TonightEnvelope(BaseModel):
    role: str
    available: bool
    ready: bool
    service_date: date
    timezone: str
    briefing_hour: int
    briefing: TonightBriefing | None


class TonightBriefingEnvelope(TonightEnvelope):
    a2ui_operations: list[FloorA2uiOperation]


class TonightLowStock(BaseModel):
    sku: str
    name: str
    on_hand: int
    par: int


class TonightStorageAlert(BaseModel):
    id: str
    zone: str
    metric: str
    status: str


class TonightDelivery(BaseModel):
    id: str
    po_number: str
    supplier: str
    expected_delivery_date: date
    status: str


class TonightApproval(BaseModel):
    id: str
    kind: str
    title: str
    status: str
    href: str | None = None


class PosAlert(BaseModel):
    kind: str
    title: str
    href: str


class TonightSensor(BaseModel):
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
    last_at: datetime | None
    stale: bool
    stale_after_hours: int
    created_at: datetime


class OpenReminder(BaseModel):
    source_type: str
    source_id: str
    rule_code: str
    title: str
    detail: str
    due_on: date
    days_left: int
    label: str
    channel: str


class TonightBoard(TonightEnvelope):
    low_stock: list[TonightLowStock]
    storage_alerts: list[TonightStorageAlert]
    deliveries_due: list[TonightDelivery]
    approvals: list[TonightApproval]
    expiring_certificates: list[CertificateGap]
    pos_alerts: list[PosAlert]
    sensors: list[TonightSensor]
    reminders: list[OpenReminder]


class LookupFilters(BaseModel):
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


class LookupHit(BaseModel):
    sku_id: str
    name: str
    producer: str
    grape: str
    region: str
    style: str
    pairing: str
    server_script: str
    flavor_profile: str
    glassware: str
    serving_temperature: str
    pour_size: str
    stock: int
    price_cents: int
    currency: str


class FloorLookup(BaseModel):
    query: str
    filters: LookupFilters
    results: list[LookupHit]
    a2ui_operations: list[FloorA2uiOperation]


class PackItem(BaseModel):
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
    stock: int
    eighty_six: bool
    cost: int | None = None
    margin_pct: float | None = None


class PackNote(BaseModel):
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


class PackCard(BaseModel):
    id: str
    product_id: str
    glassware: str
    serving_temperature: str
    pour_size: str
    decanting: str


class PackDish(BaseModel):
    id: str
    name: str
    description: str
    course: str


class PackPairing(BaseModel):
    id: str
    sku_id: str
    dish_id: str
    dish: str
    course: str
    description: str
    script: str
    pinned: bool


class LookupPack(BaseModel):
    service_date: date
    items: list[PackItem]
    notes: list[PackNote]
    cards: list[PackCard]
    dishes: list[PackDish]
    pairings: list[PackPairing]


class BriefingReportUser(BaseModel):
    user_id: str
    name: str
    acknowledged: bool
    seconds_to_ack: int | None


class BriefingReportDay(BaseModel):
    service_date: date
    briefing_id: str | None
    status: str | None
    acknowledged_count: int
    user_count: int
    users: list[BriefingReportUser]


class BriefingReport(BaseModel):
    start: date
    end: date
    days: list[BriefingReportDay]


class EightySixSku(BaseModel):
    id: str
    sku: str
    name: str
    eighty_sixed_at: datetime | None
    eighty_sixed: bool


class QuizAttemptRecord(BaseModel):
    id: Id
    user_id: Id | None
    name: str
    staff_name: str
    score: float
    score_bp: int
    answers: list[int]
    created_at: datetime


class QuizAttempts(BaseModel):
    attempts: list[QuizAttemptRecord]


class StaffBriefing(BaseModel):
    lessons: list[TrainingLesson]
    quiz: None
    roleplay: None
    a2ui_operations: list[FloorA2uiOperation]


class AuditEventRow(BaseModel):
    id: str
    seq: int
    actor_email: str
    action: str
    entity_type: str
    entity_id: str | None
    before_json: JsonValue
    after_json: JsonValue
    prev_hash: str
    event_hash: str
    created_at: datetime
    summary: str


class AuditChain(BaseModel):
    valid: bool
    checked_count: int
    head_hash: str | None
    broken_event_id: str | None
    reason: str | None


class AuditEvents(BaseModel):
    events: list[AuditEventRow]
    chain: AuditChain
    a2ui_operations: list[FloorA2uiOperation]


class VaultDocument(BaseModel):
    id: str
    doc_type: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    linked_entity_type: str
    linked_entity_id: str | None
    uploaded_by_user_id: str | None
    created_at: datetime


class VaultDocuments(BaseModel):
    documents: list[VaultDocument]


class VaultDocumentEnvelope(BaseModel):
    document: VaultDocument


class RetentionPolicy(BaseModel):
    document_retention_years: int
    can_edit: bool


class AuditPackVenue(BaseModel):
    id: str
    name: str


class AuditPackPurchase(BaseModel):
    supplier: str
    po_count: int
    invoice_count: int
    total_invoiced_cents: int
    total_received_value_cents: int


class AuditPackInvoice(BaseModel):
    invoice_number: str
    date: str
    supplier: str
    po_number: str
    total_cents: int
    status: str
    document_id: str
    download_path: str
    sha256: str
    currency: str


class AuditPackGap(BaseModel):
    purchase_order_id: str
    po_number: str
    supplier: str
    status: str
    reason: str


class AuditPackValuationLine(BaseModel):
    sku: str
    product_name: str
    unit_cost_cents: int
    start_bottles: int | float
    start_value_cents: int
    end_bottles: int | float
    end_value_cents: int


class AuditPackValuation(BaseModel):
    start_bottles: int | float
    start_value_cents: int
    end_bottles: int | float
    end_value_cents: int
    skus: list[AuditPackValuationLine]


class AuditPackCount(BaseModel):
    id: str
    status: str
    occurred_at: datetime
    location_id: str
    notes: str


class AuditPackMovement(BaseModel):
    id: str
    occurred_at: datetime
    sku: str
    product_name: str
    movement_type: str
    quantity: int | float
    quantity_delta: int | float
    cost_impact_cents: int
    actor: str
    notes: str


class AuditPackVariance(BaseModel):
    count_sessions: list[AuditPackCount]
    movements: list[AuditPackMovement]
    quantity_delta: int | float
    cost_impact_cents: int


class AuditPackWaste(BaseModel):
    movements: list[AuditPackMovement]
    cost_impact_cents: int


class AuditPackRetention(BaseModel):
    document_retention_years: int
    retain_until: date


class AuditPackChain(BaseModel):
    valid: bool
    checked: int
    checked_count: int
    head_hash: str | None
    broken_event_id: str | None
    reason: str | None


class AuditPackPreview(BaseModel):
    venue: AuditPackVenue
    start_date: date
    end_date: date
    purchases_by_supplier: list[AuditPackPurchase]
    invoice_register: list[AuditPackInvoice]
    missing_invoice_gaps: list[AuditPackGap]
    inventory_valuation: AuditPackValuation
    variance_and_shrinkage: AuditPackVariance
    comp_breakage_waste: AuditPackWaste
    retention: AuditPackRetention
    chain: AuditPackChain


class AffectedSku(BaseModel):
    sku: str
    product_name: str
    bin_code: str
    on_hand: int | float


class OpenExcursion(BaseModel):
    id: str
    zone_id: str
    reading_id: str
    metric: str
    measured_temp_c: float
    measured_humidity_pct: float
    affected_skus: list[AffectedSku]
    status: str
    created_at: datetime


class ComplianceGaps(BaseModel):
    missing_invoice_gaps: list[AuditPackGap]
    open_excursions: list[OpenExcursion]
    certificate_gaps: list[CertificateGap]
    pos_gaps: list[PosAlert]
    reminders: list[OpenReminder]
    chain: AuditPackChain


class AuditorColumn(BaseModel):
    key: str
    label: str
    type: Literal["text", "number", "money", "date"]


class AuditorLink(BaseModel):
    label: str
    href: str


class AuditorRow(BaseModel):
    id: str
    cells: dict[str, str | int | float]
    links: list[AuditorLink]


class AuditorPage(BaseModel):
    limit: int
    offset: int
    total: int


class AuditorTable(BaseModel):
    title: str
    columns: list[AuditorColumn]
    rows: list[AuditorRow]
    totals: dict[str, str | int | float]
    page: AuditorPage


class AuditQuery(BaseModel):
    audit_table: AuditorTable


ROUTES: dict[tuple[str, str], type[BaseModel]] = {
    ("GET", "/training"): StaffBriefing,
    ("GET", "/training/lessons"): TrainingLessons,
    ("POST", "/training/lessons/draft"): TrainingLesson,
    ("POST", "/training/lessons/{lesson_id}/approve"): TrainingLesson,
    ("PATCH", "/training/lessons/{lesson_id}"): TrainingLesson,
    ("GET", "/training/standards"): ServiceStandardList,
    ("PUT", "/training/standards"): ServiceStandard,
    ("POST", "/training/standards/{slug}/reset"): ServiceStandard,
    ("POST", "/training/quizzes/from-list"): TrainingQuiz,
    ("GET", "/training/quizzes/{quiz_id}"): TrainingQuiz,
    ("POST", "/training/quizzes/{quiz_id}/attempts"): TrainingQuiz,
    ("GET", "/training/reviews/due"): DueReviews,
    ("POST", "/training/roleplay"): RoleplayResponse,
    ("POST", "/training/roleplay/{session_id}/reply"): RoleplayResponse,
    ("POST", "/training/roleplay/{session_id}/score"): RoleplayResponse,
    ("GET", "/training/certificates"): CertificateList,
    ("GET", "/training/certificates/{certificate_id}"): CertificateRecord,
    ("GET", "/training/progress"): QuizAttempts,
    ("GET", "/team"): TeamRoster,
    ("GET", "/team/progress"): TeamProgress,
    ("POST", "/team/invites"): TeamInvite,
    ("POST", "/team/invites/{invite_id}/revoke"): TeamInvite,
    ("PATCH", "/team/members/{user_id}"): TeamMember,
    ("DELETE", "/team/members/{user_id}"): RemovedMember,
    ("GET", "/team/certificates"): CertificateList,
    ("GET", "/team/certificates/{certificate_id}"): CertificateRecord,
    ("POST", "/team/certificates"): CertificateEnvelope,
    ("PATCH", "/team/certificates/{certificate_id}"): CertificateEnvelope,
    ("POST", "/team/certificates/{certificate_id}/document"): CertificateEnvelope,
    ("DELETE", "/team/certificates/{certificate_id}"): DeletedCertificate,
    ("GET", "/tonight"): TonightBoard,
    ("GET", "/tonight/briefing"): TonightBriefingEnvelope,
    ("POST", "/tonight/briefing/rebuild"): TonightEnvelope,
    ("POST", "/tonight/briefing/publish"): TonightEnvelope,
    ("GET", "/tonight/briefing/report"): BriefingReport,
    ("POST", "/tonight/briefing/{briefing_id}/ack"): TonightBriefing,
    ("GET", "/lookup"): FloorLookup,
    ("GET", "/lookup/pack"): LookupPack,
    ("POST", "/cellar/skus/{sku_id}/86"): EightySixSku,
    ("DELETE", "/cellar/skus/{sku_id}/86"): EightySixSku,
    ("GET", "/compliance/audit-events"): AuditEvents,
    ("GET", "/compliance/audit-events/verify"): AuditChain,
    ("GET", "/compliance/documents"): VaultDocuments,
    ("POST", "/compliance/documents"): VaultDocumentEnvelope,
    ("GET", "/compliance/retention"): RetentionPolicy,
    ("PATCH", "/compliance/retention"): RetentionPolicy,
    ("GET", "/compliance/audit-pack/preview"): AuditPackPreview,
    ("GET", "/compliance/gaps"): ComplianceGaps,
    ("GET", "/compliance/queries/stock"): AuditQuery,
    ("GET", "/compliance/queries/conditions"): AuditQuery,
    ("GET", "/compliance/queries/compliance"): AuditQuery,
    ("GET", "/compliance/queries/pos"): AuditQuery,
    ("GET", "/compliance/queries/lists"): AuditQuery,
    ("GET", "/compliance/queries/purchases"): AuditQuery,
    ("GET", "/compliance/queries/events"): AuditQuery,
}
