"use client";

import type { LessonPayload } from "@/a2ui/lessonCardSchema";
import type { QuizPayload } from "@/a2ui/quizCardSchema";
import { ApprovalCard } from "@/components/ApprovalCard";
import { briefingPayload } from "@/a2ui/briefingCardsSchema";
import { lookupPayload } from "@/a2ui/floorLookupSchema";
import { BriefingCards } from "@/components/BriefingCards";
import { FloorLookup } from "@/components/FloorLookup";
import { LessonCard } from "@/components/LessonCard";
import { QuizCard } from "@/components/QuizCard";
import { RoleplayPanel } from "@/components/RoleplayPanel";
import { roleplaySession } from "@/a2ui/roleplayPanelSchema";
import type { ApprovalListVersion, ApprovalPurchaseOrder, ApprovalRecord } from "@/components/ApprovalCard";
import { ReceivingChecklist } from "@/components/ReceivingChecklist";
import type { ReceivingLineView, ReceivingOrder, ReceivingReceiptView } from "@/components/ReceivingChecklist";
import { asAudit, AuditTable } from "@/components/AuditTable";
import { CountSheet } from "@/components/CountSheet";
import { asReview, DishReview } from "@/components/DishReview";
import { CoverageGrid } from "@/components/CoverageGrid";
import { ListEditor } from "@/components/ListEditor";
import { asPairings, PairingGrid } from "@/components/PairingGrid";
import { asCard, asNote, ServiceCard, TastingNoteCard } from "@/components/TastingNotes";
import { VarianceReport } from "@/components/VarianceReport";
import { ZoneConditionCard } from "@/components/ZoneConditionCard";
import type { StorageZone } from "@/lib/api";

function money(n: unknown, currency?: unknown) {
  const code = typeof currency === "string" && /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  const major = Number(n || 0) / 100;
  return major.toLocaleString(undefined, { style: "currency", currency: code, maximumFractionDigits: 0 });
}

function Badge({ children, tone = "draft" }: { children: React.ReactNode; tone?: "draft" | "wine" | "ok" | "alert" }) {
  const cls =
    tone === "wine" ? "badge badge-wine" : tone === "ok" ? "badge badge-ok" : tone === "alert" ? "badge badge-alert" : "badge badge-draft";
  return <span className={cls}>{children}</span>;
}

function PairingSurface({ menuId, dishes }: { menuId: unknown; dishes: unknown }) {
  const parsed = asPairings(menuId, dishes);
  if (!parsed) return null;
  return <PairingGrid menuId={parsed.menuId} dishes={parsed.dishes} />;
}

function DishList({ dishes }: { dishes: unknown }) {
  const list = Array.isArray(dishes) ? dishes : [];
  return (
    <ul className="panel divide-y divide-line" data-testid="dish-list">
      {list.map((d: Record<string, unknown>, i: number) => (
        <li key={i} className="px-3 py-2.5">
          <div className="text-sm font-medium">{String(d.name)}</div>
          <div className="text-sm text-muted">
            {String(d.course)} · {String(d.flavor_profile)} {d.price ? `· ${money(d.price, d.currency)}` : ""}
          </div>
        </li>
      ))}
    </ul>
  );
}

function ListSummary(props: Record<string, unknown>) {
  const coverage = (props.coverage || {}) as Record<string, { count?: number; regions?: string[]; spend?: number }>;
  const gaps = Array.isArray(props.gaps) ? props.gaps : [];
  return (
    <div className="mb-4 grid gap-2 sm:grid-cols-4" data-testid="list-summary">
      <Stat label="Budget" value={money(props.budget, props.currency)} />
      <Stat label="Spent" value={money(props.spent, props.currency)} />
      <Stat label="Remaining" value={money(props.remaining, props.currency)} />
      <Stat label="Target multiple" value={`${props.targetMargin || props.target_margin || ""}x`} />
      <div className="panel p-3 text-sm sm:col-span-4">
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(coverage).map(([k, v]) => (
            <Badge key={k}>
              {k} {v.count} · {money(v.spend, props.currency)}
            </Badge>
          ))}
        </div>
        <div className="mt-2 text-muted">Gaps: {gaps.join("; ") || "none"}</div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-3">
      <div className="kicker">{label}</div>
      <div className="stat-num">{value}</div>
    </div>
  );
}

function BeverageListTable({ items }: { items: unknown }) {
  const list = Array.isArray(items) ? items : [];
  return (
    <div className="table-wrap" data-testid="beverage-list-table">
      <table>
        <thead>
          <tr>
            {["Category", "Name", "Region / style", "Cost", "Pour", "Bottle", "Margin"].map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((row: Record<string, unknown>, i: number) => (
            <tr key={i}>
              <td>{String(row.category)}</td>
              <td>
                {String(row.name)}
                <div className="text-xs text-muted">{String(row.producer)}</div>
              </td>
              <td>
                {String(row.region)}
                <div className="text-xs text-muted">{String(row.style)}</div>
              </td>
              <td>{money(row.cost, row.currency)}</td>
              <td>{row.pour_price ? money(row.pour_price, row.currency) : "—"}</td>
              <td>{row.bottle_price ? money(row.bottle_price, row.currency) : "—"}</td>
              <td>{row.margin_pct ? `${row.margin_pct}%` : `${row.pour_multiple || ""}x`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InventoryTable({ items }: { items: unknown }) {
  const list = Array.isArray(items) ? items : [];
  return (
    <div className="table-wrap" data-testid="inventory-table">
      <table>
        <thead>
          <tr>
            {["SKU", "Name", "On hand", "Par", "Depletion 30d", "Supplier"].map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((row: Record<string, unknown>) => (
            <tr key={String(row.sku)} className={row.low ? "row-low" : undefined}>
              <td className="font-mono text-xs">{String(row.sku)}</td>
              <td>{String(row.name)}</td>
              <td>
                {String(row.on_hand)} {row.low ? <Badge tone="alert">low</Badge> : null}
              </td>
              <td>{String(row.par)}</td>
              <td>{String(row.depletion_30d)}</td>
              <td>{String(row.supplier)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StockAlerts({ alerts }: { alerts: unknown }) {
  const list = Array.isArray(alerts) ? alerts : [];
  if (!list.length) return null;
  return (
    <ul className="mb-3 space-y-1" data-testid="stock-alerts">
      {list.map((a: Record<string, unknown>, i: number) => (
        <li key={i} className="banner-error">
          {String(a.message || a.name)}
        </li>
      ))}
    </ul>
  );
}

function PurchaseOrderTable({ orders }: { orders: unknown }) {
  const list = Array.isArray(orders) ? orders : [];
  return (
    <div className="space-y-3" data-testid="purchase-order-table">
      {list.map((po: Record<string, unknown>) => (
        <article key={String(po.id)} className="panel p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-medium">{String(po.supplier)}</h3>
            <Badge>DRAFT · not sent</Badge>
          </div>
          <div className="mt-1 text-sm text-muted">Total {money(po.total, po.currency)}</div>
          <ul className="mt-2 space-y-1 text-sm">
            {((po.lines as Record<string, unknown>[]) || []).map((line, i) => (
              <li key={i}>
                {String(line.sku)} · {String(line.name)} × {String(line.qty)} @ {money(line.unit_cost, line.currency || po.currency)}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

function LessonCards({ lessons }: { lessons: unknown }) {
  const list = Array.isArray(lessons) ? lessons : [];
  return (
    <div className="grid gap-2 md:grid-cols-2" data-testid="lesson-cards">
      {list.map((lesson: Record<string, unknown>) => (
        <article key={String(lesson.slug || lesson.id)} className="panel p-3">
          <Badge>{String(lesson.role)}</Badge>
          <h3 className="mt-2 text-sm font-medium">{String(lesson.title)}</h3>
          <p className="mt-2 text-sm leading-6">{String(lesson.body)}</p>
        </article>
      ))}
    </div>
  );
}

function ScheduleForm({ draft }: { draft: unknown }) {
  const d = (draft || {}) as Record<string, unknown>;
  if (!d.title) return null;
  return (
    <div className="panel mb-3 p-3" data-testid="schedule-form">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">{String(d.title)}</h3>
        <Badge>draft · not sent</Badge>
      </div>
      <p className="mt-1 text-sm text-muted">
        {String(d.supplier)} · {String(d.starts_at)} → {String(d.ends_at)}
      </p>
      <p className="text-sm text-muted">{String(d.location)}</p>
      <p className="mt-2 text-sm">{String(d.notes)}</p>
      {d.ics ? (
        <pre className="ics" data-testid="ics-block">
          {String(d.ics)}
        </pre>
      ) : null}
    </div>
  );
}

function TastingCalendar({ tastings }: { tastings: unknown }) {
  const list = Array.isArray(tastings) ? tastings : [];
  return (
    <div className="panel p-3" data-testid="tasting-calendar">
      <h3 className="text-sm font-medium">Calendar</h3>
      {list.length === 0 && <p className="mt-1 text-sm text-muted">No tastings held yet.</p>}
      <ul className="mt-2 space-y-2">
        {list.map((t: Record<string, unknown>) => (
          <li key={String(t.id)} className="border-t border-line pt-2 text-sm">
            <strong className="font-medium">{String(t.title)}</strong>
            <div className="text-muted">
              {String(t.starts_at)} · {String(t.supplier)} · {String(t.location)}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AuditSurface({ events, chain }: { events: unknown; chain: unknown }) {
  const parsed = asAudit(events, chain);
  if (!parsed) return null;
  return <AuditTable events={parsed.events} chain={parsed.chain} />;
}

function DishReviewSurface({ review }: { review: unknown }) {
  const parsed = asReview(review);
  if (!parsed) return null;
  return <DishReview key={parsed.version_id} review={parsed} />;
}

function TastingNoteSurface({ note }: { note: unknown }) {
  const parsed = asNote(note);
  if (!parsed) return null;
  return <TastingNoteCard key={parsed.id} note={parsed} />;
}

function ServiceCardSurface({ card }: { card: unknown }) {
  const parsed = asCard(card);
  if (!parsed) return null;
  return <ServiceCard key={parsed.id} card={parsed} />;
}

const CUSTOM: Record<string, (props: Record<string, unknown>) => React.ReactNode> = {
  PairingGrid: (p) => <PairingSurface menuId={p.menu_id} dishes={p.dishes} />,
  DishList: (p) => <DishList dishes={p.dishes} />,
  DishReview: (p) => <DishReviewSurface review={p.review} />,
  ListSummary: (p) => <ListSummary {...p} />,
  ListEditor: (p) => (
    <ListEditor listId={p.listId} currency={p.currency} sections={p.sections} items={p.items} candidates={p.candidates} />
  ),
  CoverageGrid: (p) => <CoverageGrid cells={p.cells} />,
  BeverageListTable: (p) => <BeverageListTable items={p.items} />,
  InventoryTable: (p) => <InventoryTable items={p.items} />,
  StockAlerts: (p) => <StockAlerts alerts={p.alerts} />,
  PurchaseOrderTable: (p) => <PurchaseOrderTable orders={p.orders} />,
  QuizCard: (p) => {
    const quiz = p.quiz as QuizPayload | undefined;
    if (!quiz || typeof quiz !== "object" || !Array.isArray(quiz.questions)) return null;
    return <QuizCard quiz={quiz} />;
  },
  RoleplayPanel: (p) => {
    const parsed = roleplaySession.safeParse(p.session);
    if (!parsed.success) return null;
    return <RoleplayPanel session={parsed.data} />;
  },
  LessonCard: (p) => {
    const lesson = p.lesson as LessonPayload | undefined;
    if (!lesson || typeof lesson !== "object" || typeof lesson.title !== "string") return null;
    return <LessonCard lesson={lesson} />;
  },
  LessonCards: (p) => <LessonCards lessons={p.lessons} />,
  BriefingCards: (p) => {
    const parsed = briefingPayload.safeParse(p.briefing);
    if (!parsed.success) return null;
    return <BriefingCards briefing={parsed.data} />;
  },
  FloorLookup: (p) => {
    const parsed = lookupPayload.safeParse(p.lookup);
    if (!parsed.success) return null;
    return <FloorLookup results={parsed.data.results} />;
  },
  ScheduleForm: (p) => <ScheduleForm draft={p.draft} />,
  TastingCalendar: (p) => <TastingCalendar tastings={p.tastings} />,
  TastingNoteCard: (p) => <TastingNoteSurface note={p.note} />,
  AuditTable: (p) => <AuditSurface events={p.events} chain={p.chain} />,
  ServiceCard: (p) => <ServiceCardSurface card={p.card} />,
  CountSheet: (p) => <CountSheet session={p.session} lines={p.lines} />,
  VarianceReport: (p) => <VarianceReport report={p.report} />,
  ApprovalCard: (p) => {
    const listVersion = p.listVersion as ApprovalListVersion | undefined;
    const approval = (p.approval as ApprovalRecord) || null;
    if (listVersion && typeof listVersion === "object" && listVersion.id) {
      return <ApprovalCard listVersion={listVersion} approval={approval} />;
    }
    const order = p.purchaseOrder as ApprovalPurchaseOrder | undefined;
    if (!order || typeof order !== "object" || !order.id) return null;
    return <ApprovalCard purchaseOrder={order} approval={approval} />;
  },
  ReceivingChecklist: (p) => {
    const order = p.purchaseOrder as ReceivingOrder | undefined;
    if (!order || typeof order !== "object" || !order.id) return null;
    return (
      <ReceivingChecklist
        purchaseOrder={order}
        receipt={(p.receipt as ReceivingReceiptView) || null}
        lines={Array.isArray(p.lines) ? (p.lines as ReceivingLineView[]) : null}
      />
    );
  },
  ZoneConditionCard: (p) => {
    const zone = p.zone as StorageZone | undefined;
    if (!zone || typeof zone !== "object" || !zone.id) return null;
    return <ZoneConditionCard zone={zone} />;
  },
};

export function renderMadiraComponent(name: string, props: Record<string, unknown>) {
  const render = CUSTOM[name];
  return render ? render(props) : null;
}
