import type { PosStatusData, UnmappedPosItem } from "@/a2ui/posSchema";

export function PosStatusView({ status }: { status: PosStatusData }) {
  const label = status.connected ? status.location_name || status.provider : "Not connected";
  return (
    <section className="panel min-w-0" data-testid="pos-status-card">
      <h2 className="text-base font-semibold">Register</h2>
      <p className="mt-2 break-words text-sm">
        {label}
        {status.masked ? ` · ${status.masked}` : ""}
      </p>
      <p className="mt-1 text-sm text-[var(--muted)]">
        {status.last_synced_at ? `Last sync ${status.last_synced_at}` : "No sync yet"}
      </p>
    </section>
  );
}

export function UnmappedPosView({ items }: { items: UnmappedPosItem[] }) {
  return (
    <section className="panel min-w-0" data-testid="pos-unmapped-card">
      <h2 className="text-base font-semibold">Unmapped items</h2>
      {items.length ? (
        <ul className="mt-2 space-y-1 text-sm">
          {items.map((item) => (
            <li key={item.variation_id || item.name} className="break-words">
              {item.name}
              {item.quantity ? ` · ${item.quantity}` : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-[var(--muted)]">Every sold item is mapped.</p>
      )}
    </section>
  );
}
