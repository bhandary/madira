"use client";

import { useState } from "react";
import type { RoleplaySession } from "@/a2ui/roleplayPanelSchema";
import { ApiError, replyRoleplay, scoreRoleplay } from "@/lib/api";

const CRITERIA = [
  ["listened", "Listened"],
  ["offered_two_options", "Offered two options"],
  ["described_structure", "Described structure"],
  ["handled_price", "Handled price"],
] as const;

const PERSONA_LABEL: Record<string, string> = {
  skeptic: "Skeptic",
  "budget-conscious": "Budget-conscious",
  connoisseur: "Connoisseur",
  celebration: "Celebration",
};

export function RoleplayPanel({
  session,
  onSession,
}: {
  session: RoleplaySession;
  onSession?: (next: RoleplaySession) => void;
}) {
  const [live, setLive] = useState(session);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (live.id !== session.id || live.transcript.length !== session.transcript.length || live.scored_at !== session.scored_at) {
    setLive(session);
  }

  function adopt(next: RoleplaySession) {
    setLive(next);
    onSession?.(next);
  }

  async function send() {
    const line = text.trim();
    if (!line || busy || live.status !== "open") return;
    setBusy(true);
    setError("");
    try {
      const next = await replyRoleplay(live.id, line);
      setText("");
      adopt(next.session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The guest did not answer.");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (busy || live.status !== "open") return;
    setBusy(true);
    setError("");
    try {
      const next = await scoreRoleplay(live.id);
      adopt(next.session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The roleplay could not be scored.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel space-y-3 p-3" data-testid="roleplay-panel">
      <p className="text-sm font-medium">
        {PERSONA_LABEL[live.persona] || live.persona}
        {live.dish_name ? ` · ${live.dish_name}` : ""}
      </p>
      <ol className="space-y-2">
        {live.transcript.map((turn, index) => (
          <li
            key={`${turn.role}-${index}`}
            className="text-sm"
            data-testid={turn.role === "guest" ? "roleplay-guest" : "roleplay-staff"}
          >
            <span className="text-muted">{turn.role === "guest" ? "Guest" : "You"}</span>
            <p>{turn.text}</p>
          </li>
        ))}
      </ol>
      {live.status === "open" && (
        <div className="space-y-2">
          <label className="lbl" htmlFor={`roleplay-reply-${live.id}`}>
            Your line
            <input
              id={`roleplay-reply-${live.id}`}
              className="field"
              data-testid="roleplay-reply"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </label>
          <button type="button" className="btn btn-primary w-full" data-testid="roleplay-send" disabled={busy || !text.trim()} onClick={() => void send()}>
            Send
          </button>
          <button type="button" className="btn btn-secondary w-full" data-testid="roleplay-finish" disabled={busy} onClick={() => void finish()}>
            Score
          </button>
        </div>
      )}
      {live.status === "scored" && live.rubric && (
        <div data-testid="roleplay-rubric" className="space-y-2">
          <p className="text-sm font-medium" data-testid="roleplay-score">
            Score {live.score}
          </p>
          <ul className="space-y-2">
            {CRITERIA.map(([key, label]) => {
              const item = live.rubric?.[key];
              if (!item) return null;
              return (
                <li key={key} className="text-sm" data-testid="roleplay-criterion">
                  <p>
                    {label} · {item.pass ? "Pass" : "Fail"}
                  </p>
                  {item.evidence ? <q>{item.evidence}</q> : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {error && (
        <p className="banner-error" role="alert" data-testid="roleplay-error">
          {error}
        </p>
      )}
    </section>
  );
}
