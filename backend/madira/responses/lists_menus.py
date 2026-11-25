"""JSON bodies for the list, menu, tasting-note, and catalog routes.

Field sets follow the dicts those routes return. UUID keys are strings in
JSON. Cent amounts and counts stay integers. Rates and markup multiples are
floats. A key that a response always includes has no default; a key that
some responses leave out does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class A2uiCreateSurface(BaseModel):
    surfaceId: str
    catalogId: str


class A2uiCreateSurfaceOperation(BaseModel):
    version: str
    createSurface: A2uiCreateSurface


class A2uiComponentUpdate(BaseModel):
    surfaceId: str
    components: list[dict[str, Any]]


class A2uiUpdateComponentsOperation(BaseModel):
    version: str
    updateComponents: A2uiComponentUpdate


class A2uiDataModelUpdate(BaseModel):
    surfaceId: str
    path: str
    value: dict[str, Any]


class A2uiUpdateDataModelOperation(BaseModel):
    version: str
    updateDataModel: A2uiDataModelUpdate


A2uiOperations = tuple[
    A2uiCreateSurfaceOperation,
    A2uiUpdateComponentsOperation,
    A2uiUpdateDataModelOperation,
]


class MenuDish(BaseModel):
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


class MenuReview(BaseModel):
    menu_id: str
    version_id: str
    name: str
    number: int
    status: str
    cuisine: str
    price_tier: str
    dishes: list[MenuDish]


class MenuIngestResult(BaseModel):
    menu_id: str
    version_id: str
    name: str
    status: str
    review: MenuReview
    a2ui_operations: A2uiOperations


class ParsedMenuDish(BaseModel):
    id: str
    name: str
    course: str
    description: str
    flavor_profile: str
    price: int
    currency: str


class MenuParseResult(BaseModel):
    menu_id: str
    name: str
    cuisine: str
    price_tier: str
    dishes: list[ParsedMenuDish]
    a2ui_operations: A2uiOperations


class MenuSummary(BaseModel):
    id: str
    name: str
    cuisine: str
    price_tier: str
    dish_count: int
    status: str


class MenusEnvelope(BaseModel):
    menus: list[MenuSummary]


class PairingSlot(BaseModel):
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


class PairingOption(BaseModel):
    sku_id: str
    name: str
    producer: str
    category: str
    style: str


class PairingDish(BaseModel):
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


class PairingGridResult(BaseModel):
    menu_id: str
    menu_name: str
    dishes: list[PairingDish]
    a2ui_operations: A2uiOperations


class MenuDetailDish(MenuDish):
    description: str
    flavor_profile: str
    content_hash: str
    pairings: list[PairingSlot]


class MenuDetail(BaseModel):
    id: str
    name: str
    cuisine: str
    price_tier: str
    raw_text: str
    version_id: str | None
    version_number: int | None
    status: str
    dishes: list[MenuDetailDish]


class TastingNote(BaseModel):
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
    approved_at: datetime | None
    has_tech_sheet: bool
    created_at: datetime


class NotesEnvelope(BaseModel):
    notes: list[TastingNote]


class ServiceCardRecord(BaseModel):
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
    approved_at: datetime | None
    created_at: datetime


class ServiceCardsEnvelope(BaseModel):
    service_cards: list[ServiceCardRecord]


class TastingDraft(BaseModel):
    note: TastingNote
    service_card: ServiceCardRecord
    a2ui_operations: A2uiOperations


class CatalogVariant(BaseModel):
    id: str
    vintage: str
    bottle_size: str
    sku_id: str


class CatalogProduct(BaseModel):
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


class ProductsEnvelope(BaseModel):
    products: list[CatalogProduct]


class CatalogSku(BaseModel):
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


class SkusEnvelope(BaseModel):
    skus: list[CatalogSku]


class PricingRule(BaseModel):
    id: str | None
    category: str
    cost_min_cents: int
    cost_max_cents: int | None
    bottle_multiple: float
    glass_pours_per_bottle: int
    glass_multiple: float
    round_to_cents: int


class PricingRulesEnvelope(BaseModel):
    source: str
    rules: list[PricingRule]


class ListItemRecord(BaseModel):
    id: str
    sku_id: str
    product_id: str
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
    bottle_size: str
    cost: int | None = None
    pour_price: int
    bottle_price: int
    currency: str
    margin_pct: float | None = None
    beverage_cost_pct: float | None = None
    rule_bottle_price: int | None = None
    rule_glass_price: int | None = None
    line_cost: int | None = None
    band: str


class ListImportItem(BaseModel):
    id: str
    sku_id: str
    product_id: str
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
    bottle_size: str
    cost: int
    pour_price: int
    bottle_price: int
    currency: str
    margin_pct: float
    beverage_cost_pct: float
    rule_bottle_price: int
    rule_glass_price: int
    line_cost: int
    band: str


class ListSectionRecord(BaseModel):
    id: str
    name: str
    position: int
    budget_share_pct: float | None
    spend: int | None = None
    item_count: int
    margin_pct: float | None = None
    beverage_cost_pct: float | None = None


class CoverageCell(BaseModel):
    category: str
    style: str
    band: str
    status: str
    product_id: str | None
    sku_id: str | None
    name: str
    dish_id: str | None
    dish_name: str


class ListCandidate(BaseModel):
    sku_id: str
    product_id: str
    name: str
    category: str
    style: str
    band: str
    cost: int | None = None


class HealthFlag(BaseModel):
    code: str
    message: str
    dish_id: str | None
    item_id: str | None
    sku_id: str | None
    section: str


class ListHealth(BaseModel):
    list_id: str
    flags: list[HealthFlag]


class CategoryCoverage(BaseModel):
    count: int
    regions: list[str]
    styles: list[str]
    spend: int


class BeverageListDetail(BaseModel):
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
    source_filename: str
    item_count: int
    items: list[ListItemRecord]
    sections: list[ListSectionRecord]
    coverage: dict[str, CategoryCoverage]
    cells: list[CoverageCell]
    suggestions: list[CoverageCell]
    gaps: list[str]
    health: ListHealth
    candidates: list[ListCandidate]
    bottles: int
    capacity_bottles: int | None


class BeverageListSurface(BeverageListDetail):
    a2ui_operations: A2uiOperations


class ListsEnvelope(BaseModel):
    lists: list[BeverageListDetail]


class CoverageReport(BaseModel):
    filled: int
    open: int
    cells: list[CoverageCell]
    suggestions: list[CoverageCell]
    list_id: str


class ListImportRow(BaseModel):
    line: int
    status: str
    action: str
    message: str
    section: str
    name: str
    producer: str
    category: str
    vintage: str
    bottle_size: str
    product_id: str | None
    variant_id: str | None


class ImportedList(BaseModel):
    id: str
    name: str
    currency: str
    item_count: int
    source_key: str
    source_filename: str
    items: list[ListImportItem]


class ListImportResult(BaseModel):
    # The JSON key is ``list``. The attribute cannot use that name: a default
    # would replace the list type while annotations are evaluated.
    model_config = ConfigDict(populate_by_name=True)

    mode: str
    currency: str
    matched: int
    new: int
    new_products: int
    new_variants: int
    errors: int
    rows: list[ListImportRow]
    imported_list: ImportedList | None = Field(default=None, alias="list")


class ListDiffRow(BaseModel):
    sku_id: str
    name: str
    section: str
    position: int
    bottle_price_cents: int
    glass_price_cents: int
    currency: str
    previous_bottle_price_cents: int | None = None
    previous_glass_price_cents: int | None = None
    previous_section: str | None = None
    previous_position: int | None = None


class ListDiff(BaseModel):
    added: list[ListDiffRow]
    removed: list[ListDiffRow]
    repriced: list[ListDiffRow]
    moved: list[ListDiffRow]
    version_id: str
    baseline_version_id: str | None
    baseline_number: int | None


class ListVersionApproval(BaseModel):
    id: str
    decision: str
    required_role: str
    comment: str
    decided_at: datetime | None


class ListVersionEntry(BaseModel):
    id: str
    sku_id: str
    section: str
    position: int
    display_name: str
    display_detail: str
    bottle_price_cents: int
    glass_price_cents: int
    currency: str


class ListVersionSection(BaseModel):
    name: str
    item_count: int
    margin_pct: float
    beverage_cost_pct: float


class ListVersionRecord(BaseModel):
    id: str
    list_id: str
    list_name: str
    number: int
    status: str
    currency: str
    approval_id: str | None
    approval: ListVersionApproval | None
    submitted_by_user_id: str | None
    published_by_user_id: str | None
    published_at: datetime | None
    document_id: str | None
    public_token: str | None
    public_path: str | None
    public_revoked_at: datetime | None
    created_at: datetime
    can_submit: bool
    can_decide: bool
    entries: list[ListVersionEntry]
    sections: list[ListVersionSection]
    diff: ListDiff


class ListVersionsEnvelope(BaseModel):
    list_id: str
    can_submit: bool
    versions: list[ListVersionRecord]


class PublicListItem(BaseModel):
    name: str
    detail: str
    bottle_price_cents: int
    glass_price_cents: int
    currency: str


class PublicListSection(BaseModel):
    name: str
    items: list[PublicListItem]


class PublicListBody(BaseModel):
    list_name: str
    number: int
    currency: str
    sections: list[PublicListSection]


class PublicList(BaseModel):
    venue_name: str
    published_at: datetime
    list: PublicListBody


ROUTES: dict[tuple[str, str], type[BaseModel]] = {
    ("GET", "/lists/pricing-rules"): PricingRulesEnvelope,
    ("PUT", "/lists/pricing-rules"): PricingRulesEnvelope,
    ("POST", "/lists/curate"): BeverageListSurface,
    ("GET", "/lists"): ListsEnvelope,
    ("GET", "/lists/{list_id}/coverage"): CoverageReport,
    ("GET", "/lists/{list_id}/health"): ListHealth,
    ("POST", "/lists/{list_id}/items"): BeverageListSurface,
    ("PATCH", "/lists/{list_id}/items/{item_id}"): BeverageListSurface,
    ("DELETE", "/lists/{list_id}/items/{item_id}"): BeverageListSurface,
    ("PUT", "/lists/{list_id}/sections"): BeverageListSurface,
    ("POST", "/lists/import"): ListImportResult,
    ("POST", "/lists/{list_id}/versions"): ListVersionRecord,
    ("GET", "/lists/{list_id}/versions"): ListVersionsEnvelope,
    ("GET", "/lists/versions/{version_id}"): ListVersionRecord,
    ("GET", "/lists/versions/{version_id}/diff"): ListDiff,
    ("POST", "/lists/versions/{version_id}/submit"): ListVersionRecord,
    ("POST", "/lists/versions/{version_id}/approve"): ListVersionRecord,
    ("POST", "/lists/versions/{version_id}/reject"): ListVersionRecord,
    ("POST", "/lists/versions/{version_id}/revoke-public"): ListVersionRecord,
    ("GET", "/public/lists/{token}"): PublicList,
    ("POST", "/menus/upload"): MenuIngestResult,
    ("POST", "/menus/ingest"): MenuIngestResult,
    ("POST", "/menus/parse"): MenuParseResult,
    ("GET", "/menus"): MenusEnvelope,
    ("GET", "/menus/{menu_id}"): MenuDetail,
    ("PATCH", "/menus/{menu_id}/versions/{version_id}/dishes/{dish_id}"): MenuIngestResult,
    ("POST", "/menus/{menu_id}/versions/{version_id}/confirm"): MenuIngestResult,
    ("GET", "/menus/{menu_id}/pairings"): PairingGridResult,
    ("POST", "/menus/{menu_id}/pair"): PairingGridResult,
    ("POST", "/menus/{menu_id}/pairings/{pairing_id}/pin"): PairingGridResult,
    ("POST", "/menus/{menu_id}/pairings/{pairing_id}/reject"): PairingGridResult,
    ("POST", "/menus/{menu_id}/pairings/{pairing_id}/swap"): PairingGridResult,
    ("GET", "/products/{product_id}/notes"): NotesEnvelope,
    ("GET", "/products/{product_id}/notes/{note_id}"): TastingNote,
    ("POST", "/products/{product_id}/notes"): TastingDraft,
    ("POST", "/products/{product_id}/notes/draft"): TastingDraft,
    ("PATCH", "/products/{product_id}/notes/{note_id}"): TastingNote,
    ("POST", "/products/{product_id}/notes/{note_id}/approve"): TastingNote,
    ("GET", "/products/{product_id}/service-cards"): ServiceCardsEnvelope,
    ("GET", "/products/{product_id}/service-cards/{card_id}"): ServiceCardRecord,
    ("PATCH", "/products/{product_id}/service-cards/{card_id}"): ServiceCardRecord,
    ("POST", "/products/{product_id}/service-cards/{card_id}/approve"): ServiceCardRecord,
    ("GET", "/products"): ProductsEnvelope,
    ("GET", "/products/{product_id}"): CatalogProduct,
    ("GET", "/skus"): SkusEnvelope,
    ("GET", "/skus/{sku_id}"): CatalogSku,
}
