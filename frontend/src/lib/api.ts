export const API = "/madira-api";

export type Delegation = {
  subagent: string;
  description: string;
  status: string;
};

export type AgentResult = {
  reply: string;
  delegation: Delegation[];
  todos: { content: string; status: string }[];
  a2ui_operations: Record<string, unknown>[];
  demo_mode: boolean;
};

export async function getStatus() {
  const res = await fetch(`${API}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("status failed");
  return res.json();
}

export async function runAgent(message: string): Promise<AgentResult> {
  const res = await fetch(`${API}/agent/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadMenu(payload: { text?: string; file?: File }) {
  const body = new FormData();
  if (payload.text) body.set("text", payload.text);
  if (payload.file) body.set("file", payload.file);
  const res = await fetch(`${API}/menus/upload`, { method: "POST", body });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getInventory() {
  const res = await fetch(`${API}/inventory`, { cache: "no-store" });
  return res.json();
}

export async function patchStock(sku: string, on_hand: number) {
  const res = await fetch(`${API}/inventory/${sku}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ on_hand }),
  });
  return res.json();
}

export async function getTraining() {
  const res = await fetch(`${API}/training`, { cache: "no-store" });
  return res.json();
}

export async function getTastings() {
  const res = await fetch(`${API}/tastings`, { cache: "no-store" });
  return res.json();
}

export async function getLists() {
  const res = await fetch(`${API}/lists`, { cache: "no-store" });
  return res.json();
}

export async function getSampleMenu() {
  const res = await fetch(`${API}/fixtures/sample-menu`, { cache: "no-store" });
  return res.json();
}
