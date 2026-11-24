/** Offline count queue. Mutation ids are stable so a replay does not double-count. */

export type QueuedCount = {
  client_mutation_id: string;
  device_id: string;
  sku: string;
  counted_quantity: number;
  counted_at: string;
  bin_qr?: string;
  notes?: string;
};

const DEVICE_KEY = "madira.device_id";

function queueKey(sessionId: string) {
  return `madira.count.queue.${sessionId}`;
}

export function deviceId() {
  const existing = localStorage.getItem(DEVICE_KEY);
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(DEVICE_KEY, created);
  return created;
}

export function mutationId(entry: Omit<QueuedCount, "client_mutation_id">) {
  return [
    "count",
    entry.device_id,
    entry.sku,
    String(entry.counted_quantity),
    entry.counted_at,
    entry.bin_qr || "",
  ].join(":");
}

export function readQueue(sessionId: string): QueuedCount[] {
  try {
    const raw = localStorage.getItem(queueKey(sessionId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((row) => row && typeof row.client_mutation_id === "string") as QueuedCount[];
  } catch {
    return [];
  }
}

export function writeQueue(sessionId: string, entries: QueuedCount[]) {
  const seen = new Set<string>();
  const unique = entries.filter((entry) => {
    if (seen.has(entry.client_mutation_id)) return false;
    seen.add(entry.client_mutation_id);
    return true;
  });
  localStorage.setItem(queueKey(sessionId), JSON.stringify(unique));
  return unique;
}

export function clearQueue(sessionId: string) {
  localStorage.removeItem(queueKey(sessionId));
}
