"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  deleteLlmSettings,
  getLlmSettings,
  notifyStatusChanged,
  saveLlmSettings,
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
  const [ready, setReady] = useState(false);
  const [gate, setGate] = useState<"" | "signin" | "forbidden">("");
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [provider, setProvider] = useState<string>("openai");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getLlmSettings()
      .then((data) => {
        setSettings(data);
        if (data.provider) setProvider(data.provider);
        setModel(data.model || "");
        setError(data.warning || "");
        notifyStatusChanged();
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          setGate("signin");
          return;
        }
        if (err instanceof ApiError && err.status === 403) {
          setGate("forbidden");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load settings.");
      })
      .finally(() => setReady(true));
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await saveLlmSettings({ provider, model, api_key: apiKey });
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
      const data = await deleteLlmSettings();
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
        variables until you remove it. The key is never shown again. Model keys are limited to the Owner.
      </p>
      {!ready ? (
        <p className="mt-6 text-sm text-muted">Checking the session…</p>
      ) : gate === "signin" ? (
        <p className="mt-6 text-sm leading-6 text-muted" data-testid="settings-signed-out">
          Sign in with the Owner account to manage model keys.{" "}
          <Link href="/login" className="font-medium text-ink">
            Continue with Google
          </Link>
        </p>
      ) : gate === "forbidden" ? (
        <p className="mt-6 text-sm leading-6 text-muted" data-testid="settings-forbidden">
          Only the Owner can change settings, billing, and model keys.
        </p>
      ) : (
        <form className="mt-6 space-y-4" onSubmit={(event) => void save(event)}>
          <p className="text-sm" data-testid="settings-mode">
            {settings?.label || "Loading settings…"}
          </p>
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
