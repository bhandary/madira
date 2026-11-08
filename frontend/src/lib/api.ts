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
  if (!res.ok) throw new Error(await errorMessage(res));
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

export type LlmSettings = {
  configured: boolean;
  stored: boolean;
  provider: string | null;
  model: string | null;
  key_hint: string | null;
  demo_mode: boolean;
  demo_forced: boolean;
  source: string;
  label: string;
  warning: string;
  default_models: Record<string, string>;
};

const TOKEN_KEY = "madira_admin_token";

export function readAdminToken(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

export function storeAdminToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAdminToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export function notifyStatusChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("madira-status"));
  }
}

async function errorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    if (typeof data.detail === "string" && data.detail) return data.detail;
  } catch {
    // The body was not JSON.
  }
  return text || `Request failed (${res.status})`;
}

function adminHeaders(token: string): HeadersInit {
  return { "X-Madira-Admin-Token": token };
}

export async function unlockSettings(password: string): Promise<string> {
  const res = await fetch(`${API}/settings/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const data = (await res.json()) as { token?: string };
  if (!data.token) throw new Error("Sign-in did not return a token.");
  return data.token;
}

export async function getLlmSettings(token: string): Promise<LlmSettings> {
  const res = await fetch(`${API}/settings/llm`, {
    headers: adminHeaders(token),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function saveLlmSettings(
  token: string,
  body: { provider: string; model: string; api_key: string }
): Promise<LlmSettings> {
  const res = await fetch(`${API}/settings/llm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...adminHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export type Account = {
  name: string;
  email: string;
  picture: string;
};

export async function getAuthConfig(): Promise<{ configured: boolean }> {
  const res = await fetch(`${API}/auth/config`, { cache: "no-store" });
  if (!res.ok) throw new Error("auth config failed");
  const data = (await res.json()) as { configured?: boolean };
  return { configured: data.configured === true };
}

export async function getAccount(): Promise<Account | null> {
  try {
    const res = await fetch(`${API}/auth/me`, { cache: "no-store", credentials: "same-origin" });
    if (!res.ok) return null;
    const data = (await res.json()) as { user?: Partial<Account> | null };
    if (!data.user || typeof data.user !== "object") return null;
    return {
      name: typeof data.user.name === "string" ? data.user.name : "",
      email: typeof data.user.email === "string" ? data.user.email : "",
      picture: typeof data.user.picture === "string" ? data.user.picture : "",
    };
  } catch {
    return null;
  }
}

export async function signOutAccount(): Promise<boolean> {
  try {
    const res = await fetch(`${API}/auth/logout`, { method: "POST", credentials: "same-origin" });
    return res.ok;
  } catch {
    return false;
  }
}

export function notifyAuthChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("madira-auth"));
  }
}

export async function deleteLlmSettings(token: string): Promise<LlmSettings> {
  const res = await fetch(`${API}/settings/llm`, {
    method: "DELETE",
    headers: adminHeaders(token),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}
