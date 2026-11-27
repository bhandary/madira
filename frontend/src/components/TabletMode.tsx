"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  clearMemberPin,
  disableTablet,
  enableTablet,
  getTablet,
  lockTablet,
  saveMyPin,
  touchTablet,
  unlockTablet,
  type TabletState,
} from "@/lib/api";

const DIGITS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"] as const;

function personLabel(person: { name: string; position: string | null; role: string }) {
  const floor = person.position ? person.position : person.role;
  return `${person.name} · ${floor}`;
}

export function TabletChrome({
  pathname,
  onRole,
}: {
  pathname: string;
  onRole: (role: string) => void;
}) {
  const [state, setState] = useState<TabletState | null>(null);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      getTablet()
        .then((next) => {
          if (cancelled) return;
          setState(next);
          if (next.actor) onRole(next.actor.role);
        })
        .catch(() => {
          if (!cancelled) setState(null);
        })
        .finally(() => {
          if (!cancelled) setReady(true);
        });
    };
    load();
    const onChange = () => load();
    const onLocked = () => {
      setState((prev) =>
        prev ? { ...prev, locked: true, actor: null, pin_session: false, expires_at: null } : prev,
      );
      setPin("");
    };
    window.addEventListener("madira-tablet", onChange);
    window.addEventListener("madira-tablet-locked", onLocked);
    return () => {
      cancelled = true;
      window.removeEventListener("madira-tablet", onChange);
      window.removeEventListener("madira-tablet-locked", onLocked);
    };
  }, [onRole]);

  useEffect(() => {
    if (!state?.actor || !state.expires_at) return;
    const end = new Date(state.expires_at).getTime();
    const delay = Math.max(0, end - Date.now());
    const timer = window.setTimeout(() => {
      void lockTablet()
        .then(setState)
        .catch(() => {
          setState((prev) =>
            prev ? { ...prev, locked: true, actor: null, pin_session: false, expires_at: null } : prev,
          );
        });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [state?.actor, state?.expires_at]);

  useEffect(() => {
    if (!state?.actor) return;
    let last = 0;
    const bump = () => {
      const now = Date.now();
      if (now - last < 30000) return;
      last = now;
      void touchTablet()
        .then(setState)
        .catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 423) {
            setState((prev) =>
              prev ? { ...prev, locked: true, actor: null, pin_session: false, expires_at: null } : prev,
            );
          }
        });
    };
    window.addEventListener("pointerdown", bump);
    window.addEventListener("keydown", bump);
    return () => {
      window.removeEventListener("pointerdown", bump);
      window.removeEventListener("keydown", bump);
    };
  }, [state?.actor]);

  async function submitPin(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    setError("");
    try {
      await saveMyPin(draft);
      setDraft("");
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the PIN.");
    }
  }

  async function submitUnlock() {
    if (busy || !selected || pin.length < 4) return;
    const attempt = pin;
    setBusy(true);
    setPin("");
    setError("");
    try {
      const next = await unlockTablet(selected, attempt);
      setState(next);
      if (next.actor) onRole(next.actor.role);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That PIN is wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (!ready || !state) return null;

  const showPinForm =
    !state.enabled && !state.pin_session && (pathname === "/" || pathname === "/settings");

  return (
    <>
      {state.actor ? (
        <div
          className="flex items-center justify-between gap-3 border-b border-line bg-panel px-4 py-2"
          data-testid="tablet-actor"
        >
          <span className="min-w-0 truncate text-sm">Signed in as {state.actor.name}</span>
          <button
            type="button"
            className="btn btn-secondary"
            data-testid="tablet-lock"
            onClick={() => {
              void lockTablet().then(setState);
            }}
          >
            Switch
          </button>
        </div>
      ) : null}
      {showPinForm ? (
        <form className="border-b border-line bg-panel px-4 py-3" onSubmit={(event) => void submitPin(event)}>
          <div className="flex min-w-0 flex-wrap items-end gap-3">
            <label className="lbl min-w-0 flex-1">
              Your tablet PIN
              <input
                className="field"
                data-testid="my-pin"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                pattern="[0-9]{4,6}"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
            </label>
            <button type="submit" className="btn btn-secondary" data-testid="my-pin-save">
              Save PIN
            </button>
          </div>
          {saved ? (
            <p className="mt-2 text-sm" data-testid="my-pin-saved">
              PIN saved.
            </p>
          ) : null}
          {error ? <p className="mt-2 text-sm text-muted">{error}</p> : null}
        </form>
      ) : null}
      {state.enabled && state.locked ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-canvas px-4 py-8" data-testid="tablet-picker">
          <div className="mx-auto w-full max-w-sm">
            <h1 className="h-page">Who is using this tablet?</h1>
            <p className="lead">Choose your name and enter your PIN.</p>
            <div className="mt-4 flex flex-col gap-2">
              {state.candidates.map((person) => (
                <button
                  key={person.user_id}
                  type="button"
                  className="btn btn-segment w-full"
                  data-testid="tablet-person"
                  data-name={person.name}
                  aria-pressed={selected === person.user_id}
                  onClick={() => {
                    setSelected(person.user_id);
                    setPin("");
                    setError("");
                  }}
                >
                  {personLabel(person)}
                </button>
              ))}
            </div>
            <p className="mt-4 text-center text-lg tracking-[0.4em]" data-testid="tablet-pin-dots" aria-hidden="true">
              {"•".repeat(pin.length)}
            </p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {DIGITS.map((digit) => (
                <button
                  key={digit}
                  type="button"
                  className="btn btn-segment"
                  data-testid={`tablet-digit-${digit}`}
                  onClick={() => setPin((current) => (current.length >= 6 ? current : current + digit))}
                >
                  {digit}
                </button>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <button type="button" className="btn btn-secondary flex-1" onClick={() => setPin((current) => current.slice(0, -1))}>
                Delete
              </button>
              <button
                type="button"
                className="btn btn-primary flex-1"
                data-testid="tablet-pin-submit"
                disabled={busy || !selected || pin.length < 4}
                onClick={() => void submitUnlock()}
              >
                Unlock
              </button>
            </div>
            {error ? (
              <p className="mt-3 text-sm" data-testid="tablet-pin-error" role="alert">
                {error}
              </p>
            ) : null}
            <EndTablet />
          </div>
        </div>
      ) : null}
    </>
  );
}

export function TabletSettings() {
  const [state, setState] = useState<TabletState | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      getTablet()
        .then((next) => {
          if (!cancelled) setState(next);
        })
        .catch(() => {
          if (!cancelled) setState(null);
        });
    };
    load();
    window.addEventListener("madira-tablet", load);
    return () => {
      cancelled = true;
      window.removeEventListener("madira-tablet", load);
    };
  }, []);

  if (!state?.can_manage) return null;

  return (
    <section className="mt-8 border-t border-line pt-6" data-testid="tablet-settings">
      <h2 className="text-lg text-ink">Shared tablet</h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        People at this venue can take a turn with their PIN. Purchase approval and settings still need a normal
        sign-in.
      </p>
      {state.enabled ? (
        <p className="mt-3 text-sm" data-testid="tablet-enabled">
          This device is a shared tablet.
        </p>
      ) : (
        <button
          type="button"
          className="btn btn-primary mt-4"
          data-testid="tablet-enable"
          disabled={!state.self_has_pin}
          onClick={() => {
            setError("");
            void enableTablet().catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Could not share this tablet.");
            });
          }}
        >
          Use this device as a shared tablet
        </button>
      )}
      {error ? <p className="mt-2 text-sm text-muted">{error}</p> : null}
      {state.clearable.length > 0 ? (
        <ul className="mt-4 flex flex-col gap-2">
          {state.clearable.map((person) => (
            <li
              key={person.user_id}
              className="flex items-center justify-between gap-3 text-sm"
              data-testid="tablet-clear-row"
              data-name={person.name}
            >
              <span className="min-w-0 truncate">{personLabel(person)}</span>
              <button
                type="button"
                className="btn btn-secondary"
                data-testid="tablet-clear-pin"
                onClick={() => {
                  void clearMemberPin(person.user_id);
                }}
              >
                Clear PIN
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {state.enabled ? <EndTablet /> : null}
    </section>
  );
}

function EndTablet() {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");

  return (
    <form
      className="mt-4 flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        setError("");
        void disableTablet(pin).catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "Could not end shared tablet mode.");
        });
      }}
    >
      <label className="lbl min-w-0 flex-1">
        Your PIN to end shared tablet mode
        <input
          className="field"
          data-testid="tablet-end-pin"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          value={pin}
          onChange={(event) => setPin(event.target.value)}
        />
      </label>
      <button type="submit" className="btn btn-secondary" data-testid="tablet-end">
        End shared tablet
      </button>
      {error ? <p className="w-full text-sm text-muted">{error}</p> : null}
    </form>
  );
}
