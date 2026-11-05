"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  clearAdminToken,
  deleteLlmSettings,
  getLlmSettings,
  notifyStatusChanged,
  readAdminToken,
  saveLlmSettings,
  storeAdminToken,
  unlockSettings,
  type LlmSettings,
} from "@/lib/api";

const PROVIDERS = [
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "google_genai", label: "Google" },
] as const;

const FALLBACK_MODELS: Record<string, string> = {
  openai: "gpt-4.1-mini",
  anthropic: "claude-haiku-4-5-20251001",
  google_genai: "gemini-3.5-flash",
};

export default function SettingsPage() {
  const passwordRef = useRef<HTMLInputElement>(null);
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [provider, setProvider] = useState<string>("openai");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(nextToken: string) {
    const data = await getLlmSettings(nextToken);
    setSettings(data);
    if (data.provider) setProvider(data.provider);
    setModel(data.model || "");
    setError(data.warning || "");
    notifyStatusChanged();
  }

  useEffect(() => {
    const existing = readAdminToken();
    void Promise.resolve().then(() => {
      if (!existing) {
        setReady(true);
        return;
      }
      setToken(existing);
      load(existing)
        .catch((err: unknown) => {
          clearAdminToken();
          setToken("");
          setError(err instanceof Error ? err.message : "Sign-in expired.");
        })
        .finally(() => setReady(true));
    });
  }, []);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const password = passwordRef.current?.value ?? "";
    if (passwordRef.current) passwordRef.current.value = "";
    setBusy(true);
    setError("");
    try {
      const next = await unlockSettings(password);
      storeAdminToken(next);
      setToken(next);
      await load(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  function lock() {
    clearAdminToken();
    setToken("");
    setSettings(null);
    setApiKey("");
    setError("");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await saveLlmSettings(token, { provider, model, api_key: apiKey });
      setApiKey("");
      setSettings(data);
      setModel(data.model || "");
      notifyStatusChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the key.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      const data = await deleteLlmSettings(token);
      setSettings(data);
      setApiKey("");
      notifyStatusChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the key.");
    } finally {
      setBusy(false);
    }
  }

  const defaults = settings?.default_models || FALLBACK_MODELS;
  const placeholder = defaults[provider] || "";

  return (
    <div data-testid="settings-page" className="max-w-lg">
      <h1 className="h-page">Settings</h1>
      <p className="lead">
        Paste a provider key to leave demo mode. It is encrypted in the database and overrides environment
        variables until you remove it. The key is never shown again.
      </p>
      {!ready ? (
        <p className="mt-6 text-sm text-muted">Checking the session…</p>
      ) : !token ? (
        <form className="mt-6 space-y-3" onSubmit={(event) => void unlock(event)}>
          <p className="text-sm leading-6 text-muted">
            Settings are locked with <span className="font-medium text-ink">MADIRA_ADMIN_PASSWORD</span>. The password is
            sent once and is not stored in the browser. This tab keeps a short-lived token until you close it or
            lock the page. If that variable is unset, the server refuses changes until you set it and restart.
          </p>
          <label className="lbl" htmlFor="settings-password">
            Admin password
            <input
              id="settings-password"
              ref={passwordRef}
              data-testid="settings-password"
              type="password"
              autoComplete="current-password"
              className="field"
            />
          </label>
          <button type="submit" data-testid="settings-unlock" disabled={busy} className="btn btn-primary">
            {busy ? "Checking…" : "Unlock"}
          </button>
          {error && (
            <p className="banner-error" role="alert" data-testid="settings-error">
              {error}
            </p>
          )}
        </form>
      ) : (
        <form className="mt-6 space-y-4" onSubmit={(event) => void save(event)}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm" data-testid="settings-mode">
              {settings?.label || "Loading settings…"}
            </p>
            <button type="button" className="btn btn-secondary" onClick={lock} data-testid="settings-lock">
              Lock
            </button>
          </div>
          {settings?.demo_forced && (
            <p className="text-sm text-muted" data-testid="settings-demo-forced">
              MADIRA_DEMO_MODE=true is forcing demo mode. A saved key is kept, and it applies after that variable
              is turned off.
            </p>
          )}
          <p className="text-sm" data-testid="settings-key-hint">
            {settings?.configured && settings.key_hint
              ? `Key set, ends in …${settings.key_hint}`
              : "No key saved in Settings."}
          </p>
          <label className="lbl" htmlFor="settings-provider">
            Provider
            <select
              id="settings-provider"
              data-testid="settings-provider"
              className="field"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
            >
              {PROVIDERS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="lbl" htmlFor="settings-model">
            Model <span className="font-normal text-muted">(optional)</span>
            <input
              id="settings-model"
              data-testid="settings-model"
              value={model}
              placeholder={placeholder}
              onChange={(event) => setModel(event.target.value)}
              className="field"
            />
          </label>
          <label className="lbl" htmlFor="settings-api-key">
            API key
            <input
              id="settings-api-key"
              data-testid="settings-api-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              className="field"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="submit" data-testid="settings-save" disabled={busy} className="btn btn-primary">
              {busy ? "Saving…" : "Save key"}
            </button>
            <button
              type="button"
              data-testid="settings-remove"
              disabled={busy || !settings?.stored}
              onClick={() => void remove()}
              className="btn btn-secondary"
            >
              Remove key
            </button>
          </div>
          {error && (
            <p className="banner-error" role="alert" data-testid="settings-error">
              {error}
            </p>
          )}
        </form>
      )}
    </div>
  );
}
