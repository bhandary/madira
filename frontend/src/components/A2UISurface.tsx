"use client";

import { applyOperations, resolveBinding, type A2UIComponent, type A2UIOperation, type SurfaceState } from "@/lib/a2ui";

function money(n: unknown) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function Badge({ children, tone = "draft" }: { children: React.ReactNode; tone?: "draft" | "wine" | "ok" | "alert" }) {
  const cls =
    tone === "wine" ? "badge badge-wine" : tone === "ok" ? "badge badge-ok" : tone === "alert" ? "badge badge-alert" : "badge badge-draft";
  return <span className={cls}>{children}</span>;
}

function PairingGrid({ dishes }: { dishes: unknown }) {
  const list = Array.isArray(dishes) ? dishes : [];
  return (
    <div className="grid gap-3" data-testid="pairing-grid">
      {list.map((dish: Record<string, unknown>, i: number) => (
        <article key={i} className="panel p-3" data-testid="pairing-card">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-medium">{String(dish.dish || dish.name)}</h3>
            <Badge tone="wine">{String(dish.course || "")}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted">
            Flavor profile: {String(dish.flavor_profile || "")}
            {dish.price ? ` · ${money(dish.price)}` : ""}
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {((dish.pairings as Record<string, unknown>[]) || []).map((p, j) => (
              <div key={j} className="rounded-md bg-panel-2 p-3" data-testid={`pairing-${p.category}`}>
                <div className="flex items-center justify-between gap-2">
                  <Badge>{String(p.category)}</Badge>
                  <span className="text-xs text-muted">{String(p.price_tier || "")}</span>
                </div>
                <div className="mt-1 text-sm font-medium">{String(p.name)}</div>
                <div className="text-xs text-muted">
                  {String(p.producer)} · {String(p.region)} · {String(p.style)}
                </div>
                <p className="mt-2 text-sm leading-5">{String(p.rationale)}</p>
                <div className="mt-2 text-xs text-muted">
                  {p.glass_price ? `Glass ${money(p.glass_price)}` : ""}
                  {p.bottle_price ? ` · Bottle ${money(p.bottle_price)}` : ""}
                </div>
              </div>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function DishList({ dishes }: { dishes: unknown }) {
  const list = Array.isArray(dishes) ? dishes : [];
  return (
    <ul className="panel divide-y divide-line" data-testid="dish-list">
      {list.map((d: Record<string, unknown>, i: number) => (
        <li key={i} className="px-3 py-2.5">
          <div className="text-sm font-medium">{String(d.name)}</div>
          <div className="text-sm text-muted">
            {String(d.course)} · {String(d.flavor_profile)} {d.price ? `· ${money(d.price)}` : ""}
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
      <Stat label="Budget" value={money(props.budget)} />
      <Stat label="Spent" value={money(props.spent)} />
      <Stat label="Remaining" value={money(props.remaining)} />
      <Stat label="Target multiple" value={`${props.targetMargin || props.target_margin || ""}x`} />
      <div className="panel p-3 text-sm sm:col-span-4">
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(coverage).map(([k, v]) => (
            <Badge key={k}>
              {k} {v.count} · {money(v.spend)}
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
      <div className="mt-1 text-lg font-medium tracking-tight">{value}</div>
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
              <td>{money(row.cost)}</td>
              <td>{row.pour_price ? money(row.pour_price) : "—"}</td>
              <td>{row.bottle_price ? money(row.bottle_price) : "—"}</td>
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
          <div className="mt-1 text-sm text-muted">Total {money(po.total)}</div>
          <ul className="mt-2 space-y-1 text-sm">
            {((po.lines as Record<string, unknown>[]) || []).map((line, i) => (
              <li key={i}>
                {String(line.sku)} · {String(line.name)} × {String(line.qty)} @ {money(line.unit_cost)}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

function QuizCard({ quiz }: { quiz: unknown }) {
  const q = (quiz || {}) as Record<string, unknown>;
  const questions = (q.questions as Record<string, unknown>[]) || [];
  const review = (q.review as Record<string, unknown>[]) || [];
  return (
    <div className="panel p-3" data-testid="quiz-card">
      <h3 className="text-base font-medium">{String(q.title || "Quiz")}</h3>
      {q.score != null && (
        <p className="mt-1 text-sm" data-testid="quiz-score">
          Score {String(q.score)}% ({String(q.correct)}/{String(q.total)})
        </p>
      )}
      <ol className="mt-3 space-y-3">
        {questions.map((item, i) => (
          <li key={i}>
            <div className="text-sm font-medium">{String(item.prompt)}</div>
            <ul className="mt-1 text-sm text-muted">
              {((item.choices as string[]) || []).map((c, idx) => (
                <li key={idx}>
                  {idx}. {c}
                </li>
              ))}
            </ul>
            {review[i] && (
              <p className="mt-1 text-sm text-ok">
                {review[i].ok ? "Correct. " : "Missed. "}
                {String(review[i].explain)}
              </p>
            )}
          </li>
        ))}
      </ol>
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

const CUSTOM: Record<string, (props: Record<string, unknown>) => React.ReactNode> = {
  PairingGrid: (p) => <PairingGrid dishes={p.dishes} />,
  DishList: (p) => <DishList dishes={p.dishes} />,
  ListSummary: (p) => <ListSummary {...p} />,
  BeverageListTable: (p) => <BeverageListTable items={p.items} />,
  InventoryTable: (p) => <InventoryTable items={p.items} />,
  StockAlerts: (p) => <StockAlerts alerts={p.alerts} />,
  PurchaseOrderTable: (p) => <PurchaseOrderTable orders={p.orders} />,
  QuizCard: (p) => <QuizCard quiz={p.quiz} />,
  LessonCards: (p) => <LessonCards lessons={p.lessons} />,
  ScheduleForm: (p) => <ScheduleForm draft={p.draft} />,
  TastingCalendar: (p) => <TastingCalendar tastings={p.tastings} />,
};

export function renderMadiraComponent(name: string, props: Record<string, unknown>) {
  const render = CUSTOM[name];
  return render ? render(props) : null;
}

function boundProps(component: A2UIComponent, data: unknown): Record<string, unknown> {
  const props: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(component)) {
    if (k === "id" || k === "component") continue;
    props[k] = resolveBinding(v, data);
  }
  return props;
}

function RenderNode({ id, surface }: { id: string; surface: SurfaceState }) {
  const component = surface.components[id];
  if (!component) return null;
  const type = component.component;
  const props = boundProps(component, surface.data);
  const custom = CUSTOM[type];
  if (custom) return <>{custom(props)}</>;

  if (type === "Text") {
    const variant = String(props.variant || "body");
    const text = String(props.text ?? "");
    if (variant === "h2") return <h2 className="mb-2 text-base font-medium">{text}</h2>;
    if (variant === "h3") return <h3 className="text-sm font-medium">{text}</h3>;
    if (variant === "caption") return <p className="kicker">{text}</p>;
    return <p className="text-sm">{text}</p>;
  }
  if (type === "Column") {
    const children = (props.children as string[]) || [];
    return (
      <div className="flex flex-col gap-3">
        {children.map((child) => (
          <RenderNode key={child} id={child} surface={surface} />
        ))}
      </div>
    );
  }
  if (type === "Row") {
    const children = (props.children as string[]) || [];
    return (
      <div className="flex flex-wrap items-center gap-2">
        {children.map((child) => (
          <RenderNode key={child} id={child} surface={surface} />
        ))}
      </div>
    );
  }
  if (type === "Card") {
    const child = String(props.child || "");
    return <div className="panel p-3">{child ? <RenderNode id={child} surface={surface} /> : null}</div>;
  }
  if (type === "Button") {
    return <button className="btn btn-primary">{String(props.child || "OK")}</button>;
  }
  if (type === "Divider") return <hr className="border-line" />;
  return (
    <div className="text-xs text-muted">
      {type} {JSON.stringify(props)}
    </div>
  );
}

export function A2UISurface({ operations }: { operations: A2UIOperation[] }) {
  const surfaces = applyOperations(operations);
  if (!surfaces.length) return null;
  return (
    <div className="a2ui-surface space-y-5" data-testid="a2ui-surface">
      {surfaces.map((surface) => (
        <section key={surface.surfaceId} data-surface={surface.surfaceId}>
          {surface.components.root ? (
            <RenderNode id="root" surface={surface} />
          ) : (
            <pre className="ics">{JSON.stringify(surface.data, null, 2)}</pre>
          )}
        </section>
      ))}
    </div>
  );
}
