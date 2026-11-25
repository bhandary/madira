from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class OpsA2uiBinding(BaseModel):
    path: str


class OpsA2uiComponent(BaseModel):
    id: str
    component: str
    children: list[str] | None = None
    text: OpsA2uiBinding | None = None
    variant: str | None = None
    status: OpsA2uiBinding | None = None
    items: OpsA2uiBinding | None = None


class OpsA2uiCreateSurface(BaseModel):
    surfaceId: str
    catalogId: str


class OpsA2uiUpdateComponents(BaseModel):
    surfaceId: str
    components: list[OpsA2uiComponent]


class OpsA2uiUpdateData(BaseModel):
    surfaceId: str
    path: str
    value: Any


class OpsA2uiOperation(BaseModel):
    version: str
    createSurface: OpsA2uiCreateSurface | None = None
    updateComponents: OpsA2uiUpdateComponents | None = None
    updateDataModel: OpsA2uiUpdateData | None = None


class PosLocation(BaseModel):
    location_id: str
    name: str


class PosStatus(BaseModel):
    connected: bool
    provider: str
    status: str
    location_id: str
    location_name: str
    key_last4: str
    masked: str
    last_synced_at: datetime | None
    watermark: str
    demo_mode: bool
    locations: list[PosLocation] | None = None
    a2ui_operations: list[OpsA2uiOperation]


class PosCatalogItem(BaseModel):
    item_id: str
    variation_id: str
    name: str
    variation_name: str
    sku_hint: str


class PosCatalog(BaseModel):
    items: list[PosCatalogItem]


class PosMapping(BaseModel):
    id: str
    provider: str
    item_id: str
    variation_id: str
    sku_id: str
    sku: str
    pour_ml: int | None
    units_per_sale: int | float


class PosMappings(BaseModel):
    mappings: list[PosMapping]


class PosMappingEnvelope(BaseModel):
    mapping: PosMapping


class PosMappingRemoved(BaseModel):
    removed: str


class PosRun(BaseModel):
    id: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    posted: int
    skipped: int
    unmapped_count: int
    error: str


class PosRuns(BaseModel):
    runs: list[PosRun]


class PosGapItem(BaseModel):
    variation_id: str
    item_id: str
    name: str
    quantity: str
    closed_at: datetime | None = None


class PosGaps(BaseModel):
    items: list[PosGapItem]
    a2ui_operations: list[OpsA2uiOperation]


class PosSyncResult(BaseModel):
    run: PosRun
    posted: int
    skipped: int
    unmapped: list[PosGapItem]


class SensorRecord(BaseModel):
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
    secret: str | None = None


class SensorList(BaseModel):
    sensors: list[SensorRecord]
    stale_after_hours: int


class SensorImportRow(BaseModel):
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


class SensorImport(BaseModel):
    id: str
    filename: str
    status: str
    rows: list[SensorImportRow]
    created_at: datetime
    decided_at: datetime | None
    posted: int | None = None
    skipped: int | None = None
    excursions: int | None = None


class SensorImports(BaseModel):
    imports: list[SensorImport]


class SensorReadingResult(BaseModel):
    status: str
    reading_id: str
    excursion: bool


class SensorWebhook(BaseModel):
    accepted: int
    duplicates: int
    readings: list[SensorReadingResult]


class ReminderRule(BaseModel):
    code: str
    title: str
    detail: str
    lead_days: int
    applies_to: str
    jurisdiction: str


class ReminderRecord(BaseModel):
    source_type: str
    source_id: str
    rule_code: str
    title: str
    detail: str
    due_on: date
    days_left: int
    label: str
    channel: str


class ReminderList(BaseModel):
    jurisdiction: str
    rules: list[ReminderRule]
    reminders: list[ReminderRecord]
    channel: str


class LicenseRecord(BaseModel):
    id: str
    label: str
    expires_on: date
    rule_code: str
    document_id: str | None


class ReminderDecision(BaseModel):
    source_type: str
    source_id: str
    status: str
    snooze_until: date | None
    channel: str


class UsageSubagent(BaseModel):
    subagent: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_micro_usd: int


class UsageDay(BaseModel):
    day: date
    calls: int
    cost_micro_usd: int


class UsageReport(BaseModel):
    month: str
    monthly_spend_cap_cents: int | None
    spent_cents: int
    spent_micro_usd: int
    requests_per_minute: int | None
    requests_this_minute: int
    by_subagent: list[UsageSubagent]
    by_day: list[UsageDay]
    cap_status: str
    can_edit: bool
    demo: bool


class LlmSettings(BaseModel):
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


class HealthResponse(BaseModel):
    status: str
    app: str
    demo_mode: bool
    llm_provider: str
    llm_model: str
    llm_source: str
    label: str
    database: str


class AgentWiring(BaseModel):
    specialists: list[str]
    has_task_tool: bool
    expected: list[str]


class StatusResponse(BaseModel):
    app: str
    demo_mode: bool
    llm_provider: str
    llm_model: str
    llm_source: str
    label: str
    database: str
    specialists: list[str]
    sample_menu: str | None = None
    wiring: AgentWiring | None = None
    wiring_error: str | None = None


class SampleMenu(BaseModel):
    text: str


class Account(BaseModel):
    name: str
    email: str
    picture: str


class AuthConfig(BaseModel):
    configured: bool


class AuthOk(BaseModel):
    ok: bool


class AuthMe(BaseModel):
    user: Account | None


class DemoPersona(BaseModel):
    slug: str
    name: str
    role: str
    position: str | None
    email: str


class DemoPersonas(BaseModel):
    active: str
    personas: list[DemoPersona]


class AguiFunctionCall(BaseModel):
    name: str
    arguments: str


class AguiToolCall(BaseModel):
    id: str
    type: Literal["function"]
    function: AguiFunctionCall


class AguiUserMessage(BaseModel):
    id: str
    role: Literal["user"]
    content: str | list[Any]
    name: str | None = None


class AguiAssistantMessage(BaseModel):
    id: str
    role: Literal["assistant"]
    content: str
    name: str | None = None
    toolCalls: list[AguiToolCall] | None = None


class AguiSystemMessage(BaseModel):
    id: str
    role: Literal["system"]
    content: str
    name: str | None = None


class AguiToolMessage(BaseModel):
    id: str
    role: Literal["tool"]
    content: str
    toolCallId: str
    error: str | None = None


class AguiReasoningMessage(BaseModel):
    id: str
    role: Literal["reasoning"]
    content: str
    encryptedValue: str | None = None


AguiThreadMessage = Annotated[
    AguiUserMessage | AguiAssistantMessage | AguiSystemMessage | AguiToolMessage | AguiReasoningMessage,
    Field(discriminator="role"),
]


class AguiThreadMessages(BaseModel):
    messages: list[AguiThreadMessage]


ROUTES: dict[tuple[str, str], type[BaseModel]] = {
    ("GET", "/pos/status"): PosStatus,
    ("GET", "/pos/catalog"): PosCatalog,
    ("GET", "/pos/mappings"): PosMappings,
    ("POST", "/pos/mappings"): PosMappingEnvelope,
    ("DELETE", "/pos/mappings/{mapping_id}"): PosMappingRemoved,
    ("GET", "/pos/runs"): PosRuns,
    ("GET", "/pos/gaps"): PosGaps,
    ("POST", "/pos/connect/demo"): PosStatus,
    ("POST", "/pos/connect/square"): PosStatus,
    ("POST", "/pos/location"): PosStatus,
    ("POST", "/pos/sync"): PosSyncResult,
    ("GET", "/sensors"): SensorList,
    ("POST", "/sensors"): SensorRecord,
    ("POST", "/sensors/{sensor_id}/rotate"): SensorRecord,
    ("GET", "/sensors/imports"): SensorImports,
    ("POST", "/sensors/imports"): SensorImport,
    ("POST", "/sensors/imports/{import_id}/apply"): SensorImport,
    ("POST", "/sensors/imports/{import_id}/reject"): SensorImport,
    ("POST", "/sensors/webhook/{sensor_key}"): SensorWebhook,
    ("GET", "/reminders"): ReminderList,
    ("POST", "/licenses"): LicenseRecord,
    ("POST", "/reminders/decide"): ReminderDecision,
    ("GET", "/usage"): UsageReport,
    ("PUT", "/usage/limits"): UsageReport,
    ("GET", "/settings/llm"): LlmSettings,
    ("POST", "/settings/llm"): LlmSettings,
    ("DELETE", "/settings/llm"): LlmSettings,
    ("GET", "/health"): HealthResponse,
    ("GET", "/status"): StatusResponse,
    ("GET", "/fixtures/sample-menu"): SampleMenu,
    ("GET", "/auth/config"): AuthConfig,
    ("GET", "/auth/csrf"): AuthOk,
    ("POST", "/auth/logout"): AuthOk,
    ("GET", "/auth/me"): AuthMe,
    ("GET", "/auth/demo-personas"): DemoPersonas,
    ("POST", "/auth/demo-persona"): DemoPersona,
    ("GET", "/ag-ui/threads/{thread_id}/messages"): AguiThreadMessages,
}
