"use client";

import { useEffect, useState } from "react";
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
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setMessage(prompt);
  }, [prompt]);
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
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]" data-testid={testId}>
      <div>
        <h1 className="font-serif text-4xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-[#5c4c3c]">{blurb}</p>
        {children}
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label className="block text-sm font-medium" htmlFor={`${testId}-prompt`}>
            Ask the Head Sommelier
          </label>
          <textarea
            id={`${testId}-prompt`}
            data-testid={`${testId}-prompt`}
            className="h-36 w-full rounded-2xl border border-gold/40 bg-white/80 p-3"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <button
            type="submit"
            data-testid={`${testId}-submit`}
            disabled={busy}
            className="rounded-full bg-burgundy px-5 py-2 text-cream disabled:opacity-60"
          >
            {busy ? "Delegating…" : "Run specialists"}
          </button>
        </form>
        {error && (
          <p className="mt-3 text-sm text-[#a33b24]" data-testid="agent-error">
            {error}
          </p>
        )}
        {result?.reply && (
          <p className="mt-4 rounded-xl bg-white/70 p-3 text-sm" data-testid="agent-reply">
            {result.reply}
          </p>
        )}
        <div className="mt-6">
          <A2UISurface operations={(result?.a2ui_operations || []) as A2UIOperation[]} />
        </div>
      </div>
      <DelegationPanel result={result} busy={busy} />
    </div>
  );
}
