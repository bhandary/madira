"""JSON bodies for purchasing, procurement, offers, sourcing, and tastings.

Fields are the keys those routes return. Calendar and file downloads are omitted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _as_id(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    return value


Id = Annotated[str, BeforeValidator(_as_id)]

Qty = int | float


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PathRef(APIModel):
    path: str


class A2uiColumn(APIModel):
    id: str
    component: str
    children: list[str]


class A2uiText(APIModel):
    id: str
    component: str
    text: PathRef
    variant: str


class A2uiPurchaseOrderTable(APIModel):
    id: str
    component: str
    orders: PathRef


class A2uiApprovalCard(APIModel):
    id: str
    component: str
    purchaseOrder: PathRef
    approval: PathRef


class A2uiInviteCard(APIModel):
    id: str
    component: str
    invite: PathRef
    approval: PathRef


class A2uiReceivingChecklist(APIModel):
    id: str
    component: str
    purchaseOrder: PathRef
    receipt: PathRef
    lines: PathRef


class A2uiScheduleForm(APIModel):
    id: str
    component: str
    draft: PathRef


class A2uiTastingCalendar(APIModel):
    id: str
    component: str
    tastings: PathRef


class A2uiSampleCard(APIModel):
    id: str
    component: str
    sample: PathRef


class A2uiSourcingBriefCard(APIModel):
    id: str
    component: str
    brief: PathRef


class A2uiRepFollowupCard(APIModel):
    id: str
    component: str
    followup: PathRef


class A2uiTastingHistoryCard(APIModel):
    id: str
    component: str
    history: PathRef


A2uiComponent = (
    A2uiColumn
    | A2uiText
    | A2uiPurchaseOrderTable
    | A2uiApprovalCard
    | A2uiInviteCard
    | A2uiReceivingChecklist
    | A2uiScheduleForm
    | A2uiTastingCalendar
    | A2uiSampleCard
    | A2uiSourcingBriefCard
    | A2uiRepFollowupCard
    | A2uiTastingHistoryCard
)


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
    rep_name: str
    rep_email: str
    rep_phone: str | None
    order_minimum_currency: str
    created_at: datetime | None
    contacts: list[SupplierContactRow]


class SupplierListItem(APIModel):
    id: Id
    name: str
    kind: str
    contact_email: str
    notes: str


class PurchaseApproval(APIModel):
    id: str
    entity_type: str
    entity_id: str
    decision: str
    required_role: str
    decided_by_user_id: str | None
    decided_at: datetime | None
    comment: str | None


class PurchaseLine(APIModel):
    id: str
    sku: str
    sku_id: str | None
    name: str
    product_name: str
    case_size: int
    cases_ordered: int
    quantity_ordered: Qty
    quantity_received: Qty
    qty: int
    unit_cost: int
    unit_cost_cents: int
    line_total_cents: int
    line_cost: int
    currency: str
    vintage: str | None
    notes: str | None


class PurchaseOrderRow(APIModel):
    id: str
    po_number: str | None
    status: str
    supplier_id: str
    supplier: str
    contact: SupplierContactRow | None
    expected_delivery_date: str | None
    subtotal_cents: int
    total: int
    currency: str
    order_minimum_cents: int
    minimum_met: bool
    shortfall_cents: int
    pdf_document_id: str | None
    sent_at: datetime | None
    sent_via: str | None
    delivery_adapter_ref: str | None
    notes: str
    created_at: datetime | None
    updated_at: datetime | None
    lines: list[PurchaseLine]
    approval: PurchaseApproval


class ReorderLocation(APIModel):
    location_id: str
    location_name: str
    quantity: Qty
    valuation_cents: int


class ReorderDraftLine(APIModel):
    id: Id
    sku: str
    name: str
    category: str
    supplier: str
    supplier_id: Id
    on_hand: Qty
    par: int
    unit_cost: int
    unit_cost_cents: int
    currency: str
    depletion_30d: Qty
    unit: str
    low: bool
    reorder_qty: int
    valuation_cents: int
    locations: list[ReorderLocation]
    qty: int
    line_cost: int


class ReorderDraftOrder(APIModel):
    id: Id
    po_number: str
    status: str
    supplier: str
    currency: str
    total: int
    minimum_met: bool
    shortfall_cents: int
    expected_delivery_date: str
    approval: PurchaseApproval
    lines: list[ReorderDraftLine]
    notes: str


class ListedPurchaseLine(APIModel):
    sku: str
    name: str
    qty: int
    unit_cost: int
    currency: str


class ListedPurchaseOrder(APIModel):
    id: Id
    status: str
    supplier: str
    notes: str
    lines: list[ListedPurchaseLine]


class SupplierProfile(APIModel):
    id: str
    name: str
    kind: str
    contact_email: str
    account_number: str | None
    default_case_size: int
    lead_time_days: int
    rep_name: str
    rep_email: str
    rep_phone: str | None
    delivery_days: list[str]
    order_minimum_cents: int
    order_minimum_currency: str
    order_minimum_label: str
    payment_terms: str | None
    notes: str


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
    created_at: datetime | None
    reviewed_at: datetime | None


class UploadedPriceSheet(PriceSheetRecord):
    source: str


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


class PriceHistoryProduct(APIModel):
    id: str
    name: str
    producer: str


class InvoiceLine(APIModel):
    sku: str
    product_name: str
    quantity: Qty
    unit_cost_cents: int
    vintage: str | None
    po_line_id: str | None


class InvoiceDocument(APIModel):
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


class InvoiceRecord(APIModel):
    id: str
    venue_id: str
    supplier_id: str
    purchase_order_id: str | None
    invoice_number: str
    invoice_date: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    document_id: str
    extracted_lines: list[InvoiceLine]
    extraction_mode: str
    status: str
    created_at: datetime | None
    filename: str
    sha256: str
    content_type: str
    document: InvoiceDocument | None = None


class DiscrepancyLine(APIModel):
    sku: str
    po_line_id: str | None
    flags: list[str]
    cost_delta_cents: int
    ordered_qty: Qty
    remaining_qty: Qty
    invoiced_qty: Qty | None
    counted_qty: Qty
    ordered_unit_cost_cents: int
    invoiced_unit_cost_cents: int | None
    ordered_vintage: str | None
    received_vintage: str | None


class DiscrepancyCounts(APIModel):
    short: int
    over: int
    invoice_qty_mismatch: int
    vintage_substitution: int
    price_change: int


class DiscrepancySummary(APIModel):
    has_discrepancies: bool
    counts: DiscrepancyCounts
    cost_delta_cents: int
    lines: list[DiscrepancyLine]


class ReceiptLineRecord(APIModel):
    id: str
    po_line_id: str | None
    sku: str
    product_name: str
    ordered_qty: Qty
    invoiced_qty: Qty | None
    counted_qty: Qty
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
    discrepancies_acknowledged: bool
    discrepancy_summary: DiscrepancySummary
    notes: str | None
    received_at: datetime | None
    accepted_at: datetime | None
    lines: list[ReceiptLineRecord]


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
    venue_id: str
    list_id: str | None
    title: str
    status: str
    created_at: datetime
    items: list[SourcingBriefItem]


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


class TastingHistoryRow(APIModel):
    supplier_id: str
    supplier: str
    product_id: str
    product: str
    tasted: int
    buy: int
    list: int
    passed: int = Field(alias="pass")
    undecided: int
    bought_bottles: int
    invoiced_bottles: int
    last_cost_cents: int | None
    last_cost_label: str


class TastingHistoryBody(APIModel):
    rows: list[TastingHistoryRow]


class InviteGapDish(APIModel):
    name: str


class InviteGap(APIModel):
    category: str
    style: str
    price_band: str
    quantity_hint: int
    dishes: list[InviteGapDish]


class AgendaSample(APIModel):
    sample_id: str
    name: str


class AgendaFacts(APIModel):
    source: str
    gaps: list[InviteGap]
    samples: list[AgendaSample]


class InviteSlot(APIModel):
    starts_at: datetime
    ends_at: datetime
    source: str
    position: int | None = None
    chosen: bool | None = None


class InviteChosenSlot(InviteSlot):
    position: int
    chosen: bool


class InviteAttendee(APIModel):
    kind: str
    name: str
    email: str
    user_id: str | None


class InviteApproval(APIModel):
    id: str
    decision: str
    required_role: str
    comment: str | None
    decided_at: datetime | None


class InvitePendingApproval(APIModel):
    decision: str
    required_role: str


class TastingInvite(APIModel):
    id: str
    session_id: str
    title: str
    supplier: str
    status: str
    agenda_note: str
    agenda_facts: AgendaFacts
    slots: list[InviteChosenSlot]
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


class TastingSessionRow(APIModel):
    id: Id
    venue_id: Id
    supplier_id: Id | None
    supplier: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str
    status: str
    notes: str
    created_by_user_id: Id | None
    created_at: datetime
    sample_count: int
    ics: str | None = None


class TastingSessionCalendarRow(TastingSessionRow):
    ics: str


class TastingDraft(APIModel):
    id: Id
    title: str
    supplier: str
    supplier_id: Id | None
    starts_at: datetime
    ends_at: datetime
    location: str
    notes: str
    status: str
    ics: str
    sent: bool


class EmptyDraft(APIModel):
    pass


class SamplePairDish(APIModel):
    dish_id: str
    name: str
    course: str
    score: int
    confidence: str


class SamplePairs(APIModel):
    profile: str
    note: str
    dishes: list[SamplePairDish]


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


class SampleCardData(APIModel):
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
    score: int | None
    note: str
    quoted_price_cents: int | None
    currency: str | None
    quoted_label: str
    decision: str
    pass_reason: str
    purchase_order_id: str | None
    purchase_order_number: str
    purchase_order_status: str
    list_id: str | None
    list_version_id: str | None
    list_version_number: int | None
    list_price: SampleListPrice
    pairs_with: SamplePairs


class A2uiCardOrder(APIModel):
    id: str
    po_number: str
    supplier: str
    status: str
    subtotal_cents: int
    order_minimum_cents: int
    minimum_met: bool
    shortfall_cents: int
    expected_delivery_date: str
    currency: str


class A2uiCardApproval(APIModel):
    id: str
    decision: str
    required_role: str
    comment: str
    decided_at: str


class PoSurfaceData(APIModel):
    title: str
    orders: list[PurchaseOrderRow | ReorderDraftOrder]


class ApprovalSurfaceData(APIModel):
    title: str
    purchaseOrder: A2uiCardOrder
    approval: A2uiCardApproval


class A2uiReceivingOrder(APIModel):
    id: str
    po_number: str
    supplier: str
    status: str


class A2uiReceivingCard(APIModel):
    id: str
    status: str
    invoice_id: str
    notes: str
    discrepancy_summary: DiscrepancySummary


class ReceivingSurfaceData(APIModel):
    title: str
    purchaseOrder: A2uiReceivingOrder
    receipt: A2uiReceivingCard
    lines: list[ReceiptLineRecord]


class TastingSurfaceData(APIModel):
    title: str
    draft: TastingDraft | EmptyDraft
    tastings: list[TastingSessionRow]


class SessionSurfaceData(APIModel):
    title: str
    session: TastingSessionRow


class SampleSurfaceData(APIModel):
    title: str
    sample: SampleCardData


class BriefSurfaceData(APIModel):
    title: str
    brief: SourcingBrief


class FollowupSurfaceData(APIModel):
    title: str
    followup: RepFollowup


class HistorySurfaceData(APIModel):
    title: str
    history: TastingHistoryBody


class InviteSurfaceData(APIModel):
    title: str
    invite: TastingInvite
    approval: InviteApproval | InvitePendingApproval


SurfaceData = (
    PoSurfaceData
    | ApprovalSurfaceData
    | ReceivingSurfaceData
    | TastingSurfaceData
    | SessionSurfaceData
    | SampleSurfaceData
    | BriefSurfaceData
    | FollowupSurfaceData
    | HistorySurfaceData
    | InviteSurfaceData
)


class A2uiCreateSurface(APIModel):
    surfaceId: str
    catalogId: str


class A2uiCreateSurfaceOp(APIModel):
    version: str
    createSurface: A2uiCreateSurface


class A2uiUpdateComponentsBody(APIModel):
    surfaceId: str
    components: list[A2uiComponent]


class A2uiUpdateComponentsOp(APIModel):
    version: str
    updateComponents: A2uiUpdateComponentsBody


class A2uiUpdateDataModelBody(APIModel):
    surfaceId: str
    path: str
    value: SurfaceData


class A2uiUpdateDataModelOp(APIModel):
    version: str
    updateDataModel: A2uiUpdateDataModelBody


A2uiOperation = A2uiCreateSurfaceOp | A2uiUpdateComponentsOp | A2uiUpdateDataModelOp


class DeletedRecord(APIModel):
    deleted: str


class DraftPurchaseOrdersResponse(APIModel):
    orders: list[ReorderDraftOrder]
    a2ui_operations: list[A2uiOperation]


class ListedPurchaseOrdersResponse(APIModel):
    orders: list[ListedPurchaseOrder]


class SupplierDirectoryResponse(APIModel):
    suppliers: list[SupplierRow]


class SupplierCreatedResponse(APIModel):
    supplier: SupplierRow


class SupplierContactCreatedResponse(APIModel):
    contact: SupplierContactRow
    supplier: SupplierRow


class PurchaseOrdersResponse(APIModel):
    orders: list[PurchaseOrderRow]


class PurchaseOrderResult(PurchaseOrderRow):
    a2ui_operations: list[A2uiOperation]


class DraftedPurchaseOrdersResponse(APIModel):
    orders: list[PurchaseOrderRow]
    a2ui_operations: list[A2uiOperation]


class InvoicesResponse(APIModel):
    invoices: list[InvoiceRecord]


class ReceiptsResponse(APIModel):
    receipts: list[ReceiptRecord]


class ReceiptResult(ReceiptRecord):
    a2ui_operations: list[A2uiOperation]


class SupplierListResponse(APIModel):
    suppliers: list[SupplierListItem]


class SupplierDeskPayload(APIModel):
    supplier: SupplierProfile
    allocations: list[AllocationRecord]
    offers: list[OfferRecord]
    current_offers: list[OfferRecord]
    price_sheets: list[PriceSheetRecord]
    products: list[CatalogChoice]


class SupplierProfileResponse(APIModel):
    supplier: SupplierProfile


class AllocationResponse(APIModel):
    allocation: AllocationRecord


class OffersResponse(APIModel):
    offers: list[OfferRecord]


class OfferResponse(APIModel):
    offer: OfferRecord


class PriceHistoryResponse(APIModel):
    product: PriceHistoryProduct
    points: list[PricePointRecord]


class PriceSheetResponse(APIModel):
    price_sheet: PriceSheetRecord


class UploadedPriceSheetResponse(APIModel):
    price_sheet: UploadedPriceSheet


class AppliedPriceSheetResponse(APIModel):
    price_sheet: PriceSheetRecord
    offers: list[OfferRecord]


class SourcingBriefsResponse(APIModel):
    briefs: list[SourcingBrief]
    brief: SourcingBrief | None = None
    a2ui_operations: list[A2uiOperation] | None = None


class SourcingBriefResponse(APIModel):
    brief: SourcingBrief
    a2ui_operations: list[A2uiOperation]


class SourcingItemResponse(APIModel):
    brief: SourcingBrief
    item_id: str
    a2ui_operations: list[A2uiOperation]


class TastingHistoryResponse(APIModel):
    rows: list[TastingHistoryRow]
    history: TastingHistoryBody
    a2ui_operations: list[A2uiOperation]


class TastingListResponse(APIModel):
    sessions: list[TastingSessionCalendarRow]
    tastings: list[TastingSessionCalendarRow]
    a2ui_operations: list[A2uiOperation]


class TastingScheduledResponse(APIModel):
    draft: TastingDraft
    sessions: list[TastingSessionRow]
    tastings: list[TastingSessionRow]
    a2ui_operations: list[A2uiOperation]


class TastingSessionResponse(APIModel):
    session: TastingSessionCalendarRow
    samples: list[SampleCardData]
    a2ui_operations: list[A2uiOperation]


class SampleResponse(APIModel):
    sample: SampleCardData
    a2ui_operations: list[A2uiOperation]


class SampleScoreResponse(APIModel):
    sample: SampleCardData
    session_id: Id
    a2ui_operations: list[A2uiOperation]


class FollowupLookupResponse(APIModel):
    followup: RepFollowup | None
    a2ui_operations: list[A2uiOperation] | None = None


class FollowupDraftResponse(APIModel):
    followup: RepFollowup
    a2ui_operations: list[A2uiOperation]


class InviteDeskResult(InviteDesk):
    a2ui_operations: list[A2uiOperation]


ROUTES: dict[tuple[str, str], type[BaseModel]] = {
    ("POST", "/purchase-orders/draft"): DraftPurchaseOrdersResponse,
    ("GET", "/purchase-orders"): ListedPurchaseOrdersResponse,
    ("GET", "/procurement/suppliers"): SupplierDirectoryResponse,
    ("POST", "/procurement/suppliers"): SupplierCreatedResponse,
    ("POST", "/procurement/suppliers/{supplier_id}/contacts"): SupplierContactCreatedResponse,
    ("GET", "/procurement/orders"): PurchaseOrdersResponse,
    ("POST", "/procurement/orders"): PurchaseOrderResult,
    ("POST", "/procurement/orders/draft-from-reorder"): DraftedPurchaseOrdersResponse,
    ("GET", "/procurement/orders/{po_id}"): PurchaseOrderResult,
    ("POST", "/procurement/orders/{po_id}/approve"): PurchaseOrderResult,
    ("POST", "/procurement/orders/{po_id}/reject"): PurchaseOrderResult,
    ("POST", "/procurement/orders/{po_id}/send"): PurchaseOrderResult,
    ("POST", "/procurement/orders/{po_id}/close"): PurchaseOrderResult,
    ("POST", "/procurement/orders/{po_id}/cancel"): PurchaseOrderResult,
    ("POST", "/procurement/orders/{po_id}/invoices"): InvoiceRecord,
    ("GET", "/procurement/invoices"): InvoicesResponse,
    ("GET", "/procurement/invoices/{invoice_id}"): InvoiceRecord,
    ("POST", "/procurement/orders/{po_id}/receipts"): ReceiptResult,
    ("GET", "/procurement/receipts"): ReceiptsResponse,
    ("GET", "/procurement/receipts/{receipt_id}"): ReceiptResult,
    ("POST", "/procurement/receipts/{receipt_id}/accept"): ReceiptResult,
    ("GET", "/suppliers"): SupplierListResponse,
    ("GET", "/procurement/suppliers/{supplier_id}/desk"): SupplierDeskPayload,
    ("PATCH", "/procurement/suppliers/{supplier_id}/profile"): SupplierProfileResponse,
    ("POST", "/procurement/suppliers/{supplier_id}/allocations"): AllocationResponse,
    ("PATCH", "/procurement/allocations/{allocation_id}"): AllocationResponse,
    ("DELETE", "/procurement/allocations/{allocation_id}"): DeletedRecord,
    ("GET", "/procurement/offers"): OffersResponse,
    ("POST", "/procurement/offers"): OfferResponse,
    ("PATCH", "/procurement/offers/{offer_id}"): OfferResponse,
    ("DELETE", "/procurement/offers/{offer_id}"): DeletedRecord,
    ("GET", "/procurement/products/{product_id}/price-history"): PriceHistoryResponse,
    ("POST", "/procurement/price-sheets"): UploadedPriceSheetResponse,
    ("GET", "/procurement/price-sheets/{sheet_id}"): PriceSheetResponse,
    ("POST", "/procurement/price-sheets/{sheet_id}/apply"): AppliedPriceSheetResponse,
    ("POST", "/procurement/price-sheets/{sheet_id}/reject"): AppliedPriceSheetResponse,
    ("GET", "/sourcing/briefs"): SourcingBriefsResponse,
    ("POST", "/sourcing/briefs"): SourcingBriefResponse,
    ("GET", "/sourcing/briefs/{brief_id}"): SourcingBriefResponse,
    ("PATCH", "/sourcing/items/{item_id}"): SourcingItemResponse,
    ("GET", "/sourcing/history"): TastingHistoryResponse,
    ("GET", "/tastings"): TastingListResponse,
    ("POST", "/tastings"): TastingScheduledResponse,
    ("GET", "/tastings/{session_id}"): TastingSessionResponse,
    ("PATCH", "/tastings/{session_id}"): TastingSessionResponse,
    ("DELETE", "/tastings/{session_id}"): DeletedRecord,
    ("POST", "/tastings/{session_id}/samples"): SampleResponse,
    ("POST", "/tastings/{session_id}/samples/label"): SampleResponse,
    ("POST", "/tastings/{session_id}/samples/{sample_id}/label"): SampleResponse,
    ("PATCH", "/tastings/{session_id}/samples/{sample_id}"): SampleResponse,
    ("DELETE", "/tastings/{session_id}/samples/{sample_id}"): DeletedRecord,
    ("POST", "/tastings/{session_id}/samples/{sample_id}/score"): SampleScoreResponse,
    ("POST", "/tastings/{session_id}/samples/{sample_id}/decision"): SampleResponse,
    ("GET", "/tastings/{session_id}/follow-up"): FollowupLookupResponse,
    ("POST", "/tastings/{session_id}/follow-up"): FollowupDraftResponse,
    ("GET", "/tastings/{session_id}/invite"): InviteDesk,
    ("POST", "/tastings/{session_id}/invite"): InviteDeskResult,
    ("POST", "/tastings/{session_id}/invite/approve"): InviteDeskResult,
    ("POST", "/tastings/{session_id}/invite/reject"): InviteDeskResult,
}
