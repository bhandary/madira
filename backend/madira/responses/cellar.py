"""JSON bodies for cellar inventory, count sessions, and storage zones."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StockLocation(BaseModel):
    location_id: str
    location_name: str
    quantity: int | float
    valuation_cents: int


class StockItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    supplier: str
    supplier_id: str | None
    on_hand: int | float
    par: int
    unit_cost: int
    unit_cost_cents: int
    currency: str
    depletion_30d: int | float
    unit: str
    low: bool
    reorder_qty: int
    valuation_cents: int
    locations: list[StockLocation]


class StockAlert(BaseModel):
    sku: str
    name: str
    on_hand: int | float
    par: int
    message: str


class CellarLocation(BaseModel):
    id: str
    name: str
    kind: str
    notes: str
    created_at: datetime


class A2uiPath(BaseModel):
    path: str


class A2uiColumn(BaseModel):
    id: str
    component: str
    children: list[str]


class A2uiText(BaseModel):
    id: str
    component: str
    text: A2uiPath
    variant: str


class A2uiStockAlerts(BaseModel):
    id: str
    component: str
    alerts: A2uiPath


class A2uiInventoryTable(BaseModel):
    id: str
    component: str
    items: A2uiPath


class A2uiCountSheet(BaseModel):
    id: str
    component: str
    session: A2uiPath
    lines: A2uiPath


class A2uiVarianceReport(BaseModel):
    id: str
    component: str
    report: A2uiPath


A2uiComponent = A2uiColumn | A2uiText | A2uiStockAlerts | A2uiInventoryTable | A2uiCountSheet | A2uiVarianceReport


class A2uiCreateSurface(BaseModel):
    surfaceId: str
    catalogId: str


class A2uiUpdateComponents(BaseModel):
    surfaceId: str
    components: list[A2uiComponent]


class A2uiCreateSurfaceOp(BaseModel):
    version: str
    createSurface: A2uiCreateSurface


class A2uiUpdateComponentsOp(BaseModel):
    version: str
    updateComponents: A2uiUpdateComponents


class InventorySurfaceData(BaseModel):
    title: str
    items: list[StockItem]
    alerts: list[StockAlert]


class InventoryDataModel(BaseModel):
    surfaceId: str
    path: str
    value: InventorySurfaceData


class InventoryDataModelOp(BaseModel):
    version: str
    updateDataModel: InventoryDataModel


InventoryA2uiOperation = A2uiCreateSurfaceOp | A2uiUpdateComponentsOp | InventoryDataModelOp


class CellarInventory(BaseModel):
    items: list[StockItem]
    alerts: list[StockAlert]
    locations: list[CellarLocation]
    a2ui_operations: list[InventoryA2uiOperation]


class CellarLocations(BaseModel):
    locations: list[CellarLocation]


class CellarLocationResult(BaseModel):
    location: CellarLocation


class CellarBin(BaseModel):
    id: str
    location_id: str
    location_name: str
    code: str
    label: str
    qr_payload: str
    created_at: datetime


class CellarBins(BaseModel):
    bins: list[CellarBin]


class CellarBinResult(BaseModel):
    bin: CellarBin


class BinLabel(BaseModel):
    bin_id: str
    code: str
    label: str
    qr_payload: str
    svg: str


class StockMovementRow(BaseModel):
    id: str
    sku_id: str
    sku: str
    name: str
    location_id: str
    location_name: str
    bin_id: str | None
    bin_code: str
    quantity: int | float
    movement_type: str
    unit_cost_cents: int | None
    source_type: str
    source_id: str
    reason: str
    actor_user_id: str | None
    created_at: datetime


class CellarMovements(BaseModel):
    movements: list[StockMovementRow]


class CellarMovementResult(BaseModel):
    movement: StockMovementRow


class CountSessionRecord(BaseModel):
    id: str
    venue_id: str
    location_id: str
    location_name: str
    status: str
    notes: str
    started_by_user_id: str | None
    submitted_by_user_id: str | None
    approved_by_user_id: str | None
    started_at: str
    submitted_at: str | None
    approved_at: str | None


class CountLineRecord(BaseModel):
    id: str
    session_id: str
    sku_id: str
    sku: str
    name: str
    bin_id: str | None
    bin_code: str
    counted_quantity: int | float
    expected_quantity: int | float | None
    device_id: str
    client_mutation_id: str
    counted_at: str
    notes: str


class CountVarianceLine(BaseModel):
    sku: str
    name: str
    counted_quantity: int | float | None
    expected_quantity: int | float
    variance: int | float | None
    variance_value_cents: int | None
    unit_cost_cents: int


class CountDeviceReading(BaseModel):
    device_id: str
    counted_quantity: int | float
    counted_at: str


class CountConflict(BaseModel):
    sku: str
    readings: list[CountDeviceReading]
    resolved: bool
    resolved_quantity: int | float | None


class CountAdjustment(BaseModel):
    id: str
    sku: str
    quantity: int | float
    movement_type: str
    source_type: str
    source_id: str
    location_id: str


class CountSheetSurfaceData(BaseModel):
    title: str
    session: CountSessionRecord
    lines: list[CountLineRecord]


class VarianceReportBody(BaseModel):
    session: CountSessionRecord
    lines: list[CountVarianceLine]
    conflicts: list[CountConflict]


class VarianceSurfaceData(BaseModel):
    title: str
    report: VarianceReportBody


class CountSheetDataModel(BaseModel):
    surfaceId: str
    path: str
    value: CountSheetSurfaceData


class CountSheetDataModelOp(BaseModel):
    version: str
    updateDataModel: CountSheetDataModel


class VarianceDataModel(BaseModel):
    surfaceId: str
    path: str
    value: VarianceSurfaceData


class VarianceDataModelOp(BaseModel):
    version: str
    updateDataModel: VarianceDataModel


CountA2uiOperation = (
    A2uiCreateSurfaceOp | A2uiUpdateComponentsOp | CountSheetDataModelOp | VarianceDataModelOp
)


class CountReport(BaseModel):
    session: CountSessionRecord
    lines: list[CountLineRecord]
    variance_lines: list[CountVarianceLine]
    conflicts: list[CountConflict]
    a2ui_operations: list[CountA2uiOperation]
    movements: list[CountAdjustment] = []


class CountSessions(BaseModel):
    sessions: list[CountSessionRecord]


class CountSyncResult(BaseModel):
    session: CountSessionRecord
    lines: list[CountLineRecord]
    conflicts: list[CountConflict]


class ParProposalRecord(BaseModel):
    id: str
    venue_id: str
    sku_id: str
    sku: str
    name: str
    current_par: int
    proposed_par: int
    depletion_30d: int | float
    lead_time_days: int
    safety_days: int
    rationale: str
    status: str
    proposed_by: str
    decided_by_user_id: str | None
    decided_at: str | None
    created_at: str | None


class ParProposals(BaseModel):
    proposals: list[ParProposalRecord]


class ParProposalResult(BaseModel):
    proposal: ParProposalRecord


class AffectedSku(BaseModel):
    sku: str
    product_name: str
    bin_code: str
    on_hand: int | float


class ZoneReading(BaseModel):
    id: str
    zone_id: str
    temp_c: float
    humidity_pct: float
    source: str
    recorded_by_user_id: str | None
    recorded_at: str
    notes: str
    in_range: bool


class ZoneExcursion(BaseModel):
    id: str
    zone_id: str
    reading_id: str
    metric: str
    measured_temp_c: float
    measured_humidity_pct: float
    affected_skus: list[AffectedSku]
    status: str
    acknowledged_by_user_id: str | None
    acknowledged_at: str | None
    resolution_note: str
    created_at: str


class StorageZone(BaseModel):
    id: str
    venue_id: str
    location_id: str | None
    location_name: str
    name: str
    target_temp_min_c: float
    target_temp_max_c: float
    target_humidity_min_pct: float
    target_humidity_max_pct: float
    notes: str
    created_at: str
    latest_reading: ZoneReading | None
    status: str
    excursion: ZoneExcursion | None


class StorageZones(BaseModel):
    zones: list[StorageZone]


class StorageZoneResult(BaseModel):
    zone: StorageZone


class ZoneReadings(BaseModel):
    readings: list[ZoneReading]


class ZoneReadingResult(BaseModel):
    reading: ZoneReading
    excursion: ZoneExcursion | None
    zone: StorageZone


class ZoneExcursions(BaseModel):
    excursions: list[ZoneExcursion]


class ZoneExcursionResult(BaseModel):
    excursion: ZoneExcursion


ROUTES: dict[tuple[str, str], type[BaseModel]] = {
    ("GET", "/inventory"): CellarInventory,
    ("PATCH", "/inventory/{sku}"): CellarInventory,
    ("GET", "/inventory/locations"): CellarLocations,
    ("POST", "/inventory/locations"): CellarLocationResult,
    ("GET", "/inventory/bins"): CellarBins,
    ("POST", "/inventory/bins"): CellarBinResult,
    ("GET", "/inventory/bins/{bin_id}/qr"): BinLabel,
    ("GET", "/inventory/movements"): CellarMovements,
    ("POST", "/inventory/movements"): CellarMovementResult,
    ("POST", "/inventory/transfers"): CellarMovements,
    ("GET", "/inventory/counts"): CountSessions,
    ("POST", "/inventory/counts"): CountSessionRecord,
    ("GET", "/inventory/counts/{session_id}"): CountReport,
    ("POST", "/inventory/counts/{session_id}/sync"): CountSyncResult,
    ("POST", "/inventory/counts/{session_id}/submit"): CountReport,
    ("POST", "/inventory/counts/{session_id}/conflicts/{sku}/resolve"): CountReport,
    ("POST", "/inventory/counts/{session_id}/approve"): CountReport,
    ("GET", "/inventory/par-proposals"): ParProposals,
    ("POST", "/inventory/par-proposals/generate"): ParProposals,
    ("POST", "/inventory/par-proposals/{proposal_id}/accept"): ParProposalResult,
    ("POST", "/inventory/par-proposals/{proposal_id}/reject"): ParProposalResult,
    ("GET", "/inventory/storage-zones"): StorageZones,
    ("POST", "/inventory/storage-zones"): StorageZoneResult,
    ("GET", "/inventory/storage-zones/{zone_id}/readings"): ZoneReadings,
    ("POST", "/inventory/storage-zones/{zone_id}/readings"): ZoneReadingResult,
    ("GET", "/inventory/excursions"): ZoneExcursions,
    ("POST", "/inventory/excursions/{excursion_id}/acknowledge"): ZoneExcursionResult,
}
