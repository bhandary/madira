"use client";

import type { AuditChain, AuditEventRow } from "@/a2ui/auditTableSchema";

export function asAudit(events: unknown, chain: unknown): { events: AuditEventRow[]; chain: AuditChain } | null {
  if (!Array.isArray(events) || !chain || typeof chain !== "object") return null;
  const status = chain as Partial<AuditChain>;
  if (typeof status.valid !== "boolean") return null;
  const rows = events.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Partial<AuditEventRow>;
    if (typeof row.id !== "string" || typeof row.action !== "string") return [];
    return [
      {
        id: row.id,
        seq: Number(row.seq || 0),
        actor_email: typeof row.actor_email === "string" ? row.actor_email : "",
        action: row.action,
        entity_type: typeof row.entity_type === "string" ? row.entity_type : "",
        entity_id: typeof row.entity_id === "string" ? row.entity_id : null,
        before_json: row.before_json && typeof row.before_json === "object" ? row.before_json : null,
        after_json: row.after_json && typeof row.after_json === "object" ? row.after_json : null,
        prev_hash: typeof row.prev_hash === "string" ? row.prev_hash : "",
        event_hash: typeof row.event_hash === "string" ? row.event_hash : "",
        created_at: typeof row.created_at === "string" ? row.created_at : "",
        summary: typeof row.summary === "string" ? row.summary : "",
      },
    ];
  });
  return {
    events: rows,
    chain: {
      valid: status.valid,
      checked_count: Number(status.checked_count || 0),
      head_hash: typeof status.head_hash === "string" ? status.head_hash : null,
      broken_event_id: typeof status.broken_event_id === "string" ? status.broken_event_id : null,
      reason: typeof status.reason === "string" ? status.reason : null,
    },
  };
}

export function ChainBadge({ chain }: { chain: AuditChain }) {
  const tone = chain.valid ? "badge badge-ok" : "badge badge-alert";
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="chain-status-row">
      <span className={tone} data-testid="chain-status">
        {chain.valid ? "Verified" : "Broken"}
      </span>
      <span className="text-muted">
        {chain.checked_count} event{chain.checked_count === 1 ? "" : "s"} checked
        {chain.valid && chain.head_hash ? ` · head ${chain.head_hash.slice(0, 12)}` : ""}
        {!chain.valid && chain.reason ? ` · ${chain.reason}` : ""}
      </span>
    </p>
  );
}

export function AuditTable({ events, chain }: { events: AuditEventRow[]; chain?: AuditChain | null }) {
  return (
    <div data-testid="audit-table">
      {chain ? <ChainBadge chain={chain} /> : null}
      <div className="table-wrap mt-3">
        <table>
          <thead>
            <tr>
              {["Seq", "When", "Actor", "Action", "Entity", "Before / after"].map((heading) => (
                <th key={heading}>{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={6}>No audit events for this filter.</td>
              </tr>
            ) : (
              events.map((event) => (
                <tr key={event.id} data-testid="audit-row">
                  <td className="font-mono">{event.seq}</td>
                  <td className="whitespace-nowrap">{event.created_at.replace("T", " ").replace("Z", " UTC")}</td>
                  <td>{event.actor_email || "—"}</td>
                  <td className="font-mono text-xs">{event.action}</td>
                  <td>
                    {event.entity_type || "—"}
                    {event.entity_id ? <div className="text-xs text-muted">{event.entity_id.slice(0, 8)}</div> : null}
                  </td>
                  <td>{event.summary || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
