"use client";

import { useState } from "react";
import { A2UISurface } from "@/components/A2UISurface";
import { DelegationPanel } from "@/components/DelegationPanel";
import { runAgent, type AgentResult } from "@/lib/api";
import type { A2UIOperation } from "@/lib/a2ui";

export function AgentWorkbench({
  title,
  blurb,
  prompt,
  children,
  testId,
}: {
  title: string;
  blurb: string;
  prompt: string;
  children?: React.ReactNode;
  testId: string;
}) {
  const [message, setMessage] = useState(prompt);
  const [seenPrompt, setSeenPrompt] = useState(prompt);
  const [busy, setBusy] = useState(false);

  if (prompt !== seenPrompt) {
    setSeenPrompt(prompt);
    setMessage(prompt);
  }
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentResult | null>(null);

  async function submit(next?: string) {
    const payload = next ?? message;
    setMessage(payload);
    setBusy(true);
    setError(null);
    try {
      const out = await runAgent(payload);
      setResult(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "run failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_16rem]" data-testid={testId}>
      <div className="min-w-0">
        <h1 className="h-page">{title}</h1>
        <p className="lead">{blurb}</p>
        {children}
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label className="lbl" htmlFor={`${testId}-prompt`}>
            Ask the Head Sommelier
            <textarea
              id={`${testId}-prompt`}
              data-testid={`${testId}-prompt`}
              className="field-area"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </label>
          <button type="submit" data-testid={`${testId}-submit`} disabled={busy} className="btn btn-primary">
            {busy ? "Delegating…" : "Run specialists"}
          </button>
        </form>
        {error && (
          <p className="banner-error mt-3" role="alert" data-testid="agent-error">
            {error}
          </p>
        )}
        {result?.reply && (
          <p className="panel mt-4 p-3 text-sm leading-6" data-testid="agent-reply">
            {result.reply}
          </p>
        )}
        <div className="mt-5">
          <A2UISurface operations={(result?.a2ui_operations || []) as A2UIOperation[]} />
        </div>
      </div>
      <DelegationPanel result={result} busy={busy} />
    </div>
  );
}
