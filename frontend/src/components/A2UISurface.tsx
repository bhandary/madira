"use client";

import { applyOperations, resolveBinding, type A2UIComponent, type A2UIOperation, type SurfaceState } from "@/lib/a2ui";

function money(n: unknown) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function Badge({ children, tone = "gold" }: { children: React.ReactNode; tone?: "gold" | "wine" | "ok" | "alert" }) {
  const cls =
    tone === "wine"
      ? "bg-burgundy text-cream"
      : tone === "ok"
        ? "bg-[#2f4a3c] text-cream"
        : tone === "alert"
          ? "bg-[#a33b24] text-cream"
          : "bg-gold/20 text-ink border border-gold/40";
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] tracking-wide ${cls}`}>{children}</span>;
}

function PairingGrid({ dishes }: { dishes: unknown }) {
  const list = Array.isArray(dishes) ? dishes : [];
  return (
    <div className="grid gap-4" data-testid="pairing-grid">
      {list.map((dish: Record<string, unknown>, i: number) => (
        <article key={i} className="rounded-2xl border border-gold/30 bg-white/70 p-4 shadow-sm" data-testid="pairing-card">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-serif text-xl">{String(dish.dish || dish.name)}</h3>
            <Badge tone="wine">{String(dish.course || "")}</Badge>
          </div>
          <p className="mt-1 text-sm text-[#5c4c3c]">
            Flavor profile: {String(dish.flavor_profile || "")}
            {dish.price ? ` · ${money(dish.price)}` : ""}
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {((dish.pairings as Record<string, unknown>[]) || []).map((p, j) => (
              <div key={j} className="rounded-xl bg-cream/80 p-3" data-testid={`pairing-${p.category}`}>
                <div className="flex items-center justify-between gap-2">
                  <Badge>{String(p.category)}</Badge>
                  <span className="text-xs">{String(p.price_tier || "")}</span>
                </div>
                <div className="mt-1 font-medium">{String(p.name)}</div>
                <div className="text-xs text-[#5c4c3c]">
                  {String(p.producer)} · {String(p.region)} · {String(p.style)}
                </div>
                <p className="mt-2 text-sm leading-5">{String(p.rationale)}</p>
                <div className="mt-2 text-xs">
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
    <ul className="divide-y divide-gold/30 rounded-2xl border border-gold/30 bg-white/70" data-testid="dish-list">
      {list.map((d: Record<string, unknown>, i: number) => (
        <li key={i} className="px-4 py-3">
          <div className="font-medium">{String(d.name)}</div>
          <div className="text-sm text-[#5c4c3c]">
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
    <div className="mb-4 grid gap-3 sm:grid-cols-4" data-testid="list-summary">
      <Stat label="Budget" value={money(props.budget)} />
      <Stat label="Spent" value={money(props.spent)} />
      <Stat label="Remaining" value={money(props.remaining)} />
      <Stat label="Target multiple" value={`${props.targetMargin || props.target_margin || ""}x`} />
      <div className="sm:col-span-4 rounded-xl border border-gold/30 bg-white/70 p-3 text-sm">
        Coverage:{" "}
        {Object.entries(coverage).map(([k, v]) => (
          <Badge key={k}>
            {k} {v.count} · {money(v.spend)}
          </Badge>
        ))}
        <div className="mt-2">Gaps: {gaps.join("; ") || "none"}</div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gold/30 bg-white/70 p-3">
      <div className="text-[11px] uppercase tracking-widest text-[#7a6a58]">{label}</div>
      <div className="font-serif text-2xl">{value}</div>
    </div>
  );
}

function BeverageListTable({ items }: { items: unknown }) {
  const list = Array.isArray(items) ? items : [];
  return (
    <div className="overflow-x-auto rounded-2xl border border-gold/30 bg-white/80" data-testid="beverage-list-table">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-burgundy text-cream">
          <tr>
            {["Category", "Name", "Region / style", "Cost", "Pour", "Bottle", "Margin"].map((h) => (
              <th key={h} className="px-3 py-2 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((row: Record<string, unknown>, i: number) => (
            <tr key={i} className="border-t border-gold/20">
              <td className="px-3 py-2">{String(row.category)}</td>
              <td className="px-3 py-2">
                {String(row.name)}
                <div className="text-xs text-[#7a6a58]">{String(row.producer)}</div>
              </td>
              <td className="px-3 py-2">
                {String(row.region)}
                <div className="text-xs">{String(row.style)}</div>
              </td>
              <td className="px-3 py-2">{money(row.cost)}</td>
              <td className="px-3 py-2">{row.pour_price ? money(row.pour_price) : "—"}</td>
              <td className="px-3 py-2">{row.bottle_price ? money(row.bottle_price) : "—"}</td>
              <td className="px-3 py-2">{row.margin_pct ? `${row.margin_pct}%` : `${row.pour_multiple || ""}x`}</td>
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
    <div className="overflow-x-auto rounded-2xl border border-gold/30 bg-white/80" data-testid="inventory-table">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-burgundy text-cream">
          <tr>
            {["SKU", "Name", "On hand", "Par", "Depletion 30d", "Supplier"].map((h) => (
              <th key={h} className="px-3 py-2 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((row: Record<string, unknown>) => (
            <tr key={String(row.sku)} className={`border-t border-gold/20 ${row.low ? "bg-red-50" : ""}`}>
              <td className="px-3 py-2 font-mono text-xs">{String(row.sku)}</td>
              <td className="px-3 py-2">{String(row.name)}</td>
              <td className="px-3 py-2">
                {String(row.on_hand)} {row.low ? <Badge tone="alert">low</Badge> : null}
              </td>
              <td className="px-3 py-2">{String(row.par)}</td>
              <td className="px-3 py-2">{String(row.depletion_30d)}</td>
              <td className="px-3 py-2">{String(row.supplier)}</td>
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
        <li key={i} className="rounded-lg bg-red-50 px-3 py-2 text-sm text-[#a33b24]">
          {String(a.message || a.name)}
        </li>
      ))}
    </ul>
  );
}

function PurchaseOrderTable({ orders }: { orders: unknown }) {
  const list = Array.isArray(orders) ? orders : [];
  return (
    <div className="space-y-4" data-testid="purchase-order-table">
      {list.map((po: Record<string, unknown>) => (
        <article key={String(po.id)} className="rounded-2xl border border-gold/30 bg-white/80 p-4">
          <div className="flex justify-between">
            <h3 className="font-serif text-xl">{String(po.supplier)}</h3>
            <Badge tone="gold">DRAFT · not sent</Badge>
          </div>
          <div className="text-sm">Total {money(po.total)}</div>
          <ul className="mt-2 text-sm">
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
    <div className="rounded-2xl border border-gold/30 bg-white/80 p-4" data-testid="quiz-card">
      <h3 className="font-serif text-2xl">{String(q.title || "Quiz")}</h3>
      {q.score != null && (
        <p className="mt-1 text-lg" data-testid="quiz-score">
          Score {String(q.score)}% ({String(q.correct)}/{String(q.total)})
        </p>
      )}
      <ol className="mt-3 space-y-3">
        {questions.map((item, i) => (
          <li key={i}>
            <div className="font-medium">{String(item.prompt)}</div>
            <ul className="mt-1 text-sm">
              {((item.choices as string[]) || []).map((c, idx) => (
                <li key={idx}>
                  {idx}. {c}
                </li>
              ))}
            </ul>
            {review[i] && (
              <p className="mt-1 text-sm text-[#2f4a3c]">
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
    <div className="grid gap-3 md:grid-cols-2" data-testid="lesson-cards">
      {list.map((lesson: Record<string, unknown>) => (
        <article key={String(lesson.slug || lesson.id)} className="rounded-2xl border border-gold/30 bg-white/80 p-4">
          <Badge>{String(lesson.role)}</Badge>
          <h3 className="mt-2 font-serif text-xl">{String(lesson.title)}</h3>
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
    <div className="mb-4 rounded-2xl border border-gold/30 bg-white/80 p-4" data-testid="schedule-form">
      <div className="flex justify-between">
        <h3 className="font-serif text-xl">{String(d.title)}</h3>
        <Badge tone="gold">draft · not sent</Badge>
      </div>
      <p className="text-sm">
        {String(d.supplier)} · {String(d.starts_at)} → {String(d.ends_at)}
      </p>
      <p className="text-sm">{String(d.location)}</p>
      <p className="mt-2 text-sm">{String(d.notes)}</p>
      {d.ics ? (
        <pre className="mt-3 max-h-40 overflow-auto rounded bg-cream p-2 text-xs" data-testid="ics-block">
          {String(d.ics)}
        </pre>
      ) : null}
    </div>
  );
}

function TastingCalendar({ tastings }: { tastings: unknown }) {
  const list = Array.isArray(tastings) ? tastings : [];
  return (
    <div className="rounded-2xl border border-gold/30 bg-white/80 p-4" data-testid="tasting-calendar">
      <h3 className="font-serif text-xl">Calendar</h3>
      {list.length === 0 && <p className="text-sm">No tastings held yet.</p>}
      <ul className="mt-2 space-y-2">
        {list.map((t: Record<string, unknown>) => (
          <li key={String(t.id)} className="border-t border-gold/20 pt-2 text-sm">
            <strong>{String(t.title)}</strong>
            <div>
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
    if (variant === "h2") return <h2 className="mb-3 font-serif text-3xl">{text}</h2>;
    if (variant === "h3") return <h3 className="font-serif text-xl">{text}</h3>;
    if (variant === "caption") return <p className="text-xs uppercase tracking-widest text-[#7a6a58]">{text}</p>;
    return <p>{text}</p>;
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
      <div className="flex flex-wrap items-center gap-3">
        {children.map((child) => (
          <RenderNode key={child} id={child} surface={surface} />
        ))}
      </div>
    );
  }
  if (type === "Card") {
    const child = String(props.child || "");
    return (
      <div className="rounded-2xl border border-gold/30 bg-white/80 p-4">
        {child ? <RenderNode id={child} surface={surface} /> : null}
      </div>
    );
  }
  if (type === "Button") {
    return <button className="rounded-full bg-burgundy px-4 py-2 text-cream">{String(props.child || "OK")}</button>;
  }
  if (type === "Divider") return <hr className="border-gold/30" />;
  return (
    <div className="text-xs text-[#7a6a58]">
      {type} {JSON.stringify(props)}
    </div>
  );
}

export function A2UISurface({ operations }: { operations: A2UIOperation[] }) {
  const surfaces = applyOperations(operations);
  if (!surfaces.length) return null;
  return (
    <div className="a2ui-surface space-y-6" data-testid="a2ui-surface">
      {surfaces.map((surface) => (
        <section key={surface.surfaceId} data-surface={surface.surfaceId}>
          {surface.components.root ? (
            <RenderNode id="root" surface={surface} />
          ) : (
            <pre className="text-xs">{JSON.stringify(surface.data, null, 2)}</pre>
          )}
        </section>
      ))}
    </div>
  );
}
