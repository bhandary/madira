"use client";

import { useEffect, useState } from "react";
import { CopilotChatMessageView, useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { DelegationPanel, type DelegationRow } from "@/components/DelegationPanel";
import { HoverArrow } from "@/components/HoverArrow";
import { useStoredThreadId } from "@/lib/thread";

const RUNTIME_AGENT = "head_sommelier";

type ToolCall = {
  id?: string;
  function?: { name?: string; arguments?: unknown };
};

type StreamMessage = {
  id?: string;
  role?: string;
  toolCalls?: ToolCall[];
  toolCallId?: string;
  tool_call_id?: string;
};

function parseArgs(raw: unknown): Record<string, unknown> | null {
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as unknown;
      return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }
  if (raw && typeof raw === "object") return raw as Record<string, unknown>;
  return null;
}

function delegationFrom(messages: StreamMessage[]): DelegationRow[] {
  const done = new Set<string>();
  for (const message of messages) {
    const callId = message.toolCallId || message.tool_call_id;
    if (message.role === "tool" && callId) done.add(callId);
  }
  const rows: DelegationRow[] = [];
  const seen = new Set<string>();
  for (const message of messages) {
    for (const call of message.toolCalls ?? []) {
      if (call.function?.name !== "task" || !call.id || seen.has(call.id)) continue;
      const args = parseArgs(call.function.arguments);
      const subagent = typeof args?.subagent_type === "string" ? args.subagent_type : "";
      if (!subagent) continue;
      seen.add(call.id);
      rows.push({
        id: call.id,
        subagent,
        description: typeof args?.description === "string" ? args.description : "",
        status: done.has(call.id) ? "complete" : "working",
      });
    }
  }
  return rows;
}

function todosFrom(messages: StreamMessage[]): { content: string; status: string }[] {
  let latest: { content: string; status: string }[] = [];
  for (const message of messages) {
    for (const call of message.toolCalls ?? []) {
      if (call.function?.name !== "write_todos") continue;
      const args = parseArgs(call.function.arguments);
      if (!Array.isArray(args?.todos)) continue;
      latest = args.todos.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const todo = item as { content?: unknown; status?: unknown };
        if (typeof todo.content !== "string") return [];
        return [{ content: todo.content, status: typeof todo.status === "string" ? todo.status : "" }];
      });
    }
  }
  return latest;
}

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
  const threadId = useStoredThreadId(`madira-thread:${testId}`);

  if (!threadId) {
    return (
      <WorkbenchFrame title={title} blurb={blurb} testId={testId} message={prompt} busy={false} ready={false} error={null} onMessage={() => undefined} onSubmit={() => undefined}>
        {children}
      </WorkbenchFrame>
    );
  }
  return (
    <WorkbenchSession title={title} blurb={blurb} prompt={prompt} testId={testId} threadId={threadId}>
      {children}
    </WorkbenchSession>
  );
}

function WorkbenchSession({
  title,
  blurb,
  prompt,
  children,
  testId,
  threadId,
}: {
  title: string;
  blurb: string;
  prompt: string;
  children?: React.ReactNode;
  testId: string;
  threadId: string;
}) {
  const { copilotkit } = useCopilotKit();
  const { agent, isReady } = useAgent({
    agentId: testId,
    runtimeAgentId: RUNTIME_AGENT,
    threadId,
  });
  const [message, setMessage] = useState(prompt);
  const [seenPrompt, setSeenPrompt] = useState(prompt);
  const [busy, setBusy] = useState(false);
  const [restored, setRestored] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (prompt !== seenPrompt) {
    setSeenPrompt(prompt);
    setMessage(prompt);
  }

  useEffect(() => {
    const subscription = agent.subscribe({
      onRunErrorEvent: ({ event }) => {
        const text = typeof event.message === "string" ? event.message.trim() : "";
        setError(text || "The sommelier could not complete the request.");
      },
    });
    return () => subscription.unsubscribe();
  }, [agent]);

  useEffect(() => {
    if (!isReady) return;
    let cancelled = false;
    void copilotkit
      .connectAgent({ agent })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setRestored(true);
      });
    return () => {
      cancelled = true;
    };
  }, [agent, copilotkit, isReady, threadId]);

  const messages = (agent.messages ?? []) as StreamMessage[];
  const running = busy || (restored && agent.isRunning);

  async function submit(next?: string) {
    const payload = (next ?? message).trim();
    if (!payload || !restored || running) return;
    setMessage(payload);
    setBusy(true);
    setError(null);
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content: payload });
    try {
      await agent.runAgent();
    } catch (err) {
      const text = err instanceof Error ? err.message.trim() : "";
      setError(text || "The sommelier could not complete the request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <WorkbenchFrame
      title={title}
      blurb={blurb}
      testId={testId}
      message={message}
      busy={running}
      ready={restored && isReady}
      error={error}
      onMessage={setMessage}
      onSubmit={() => void submit()}
      delegation={delegationFrom(messages)}
      todos={todosFrom(messages)}
      messages={agent.messages}
    >
      {children}
    </WorkbenchFrame>
  );
}

function WorkbenchFrame({
  title,
  blurb,
  testId,
  message,
  busy,
  ready,
  error,
  onMessage,
  onSubmit,
  children,
  delegation = [],
  todos = [],
  messages = [],
}: {
  title: string;
  blurb: string;
  testId: string;
  message: string;
  busy: boolean;
  ready: boolean;
  error: string | null;
  onMessage: (value: string) => void;
  onSubmit: () => void;
  children?: React.ReactNode;
  delegation?: DelegationRow[];
  todos?: { content: string; status: string }[];
  messages?: unknown[];
}) {
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
            onSubmit();
          }}
        >
          <label className="lbl" htmlFor={`${testId}-prompt`}>
            Ask the Head Sommelier
            <textarea
              id={`${testId}-prompt`}
              data-testid={`${testId}-prompt`}
              className="field-area"
              value={message}
              onChange={(e) => onMessage(e.target.value)}
            />
          </label>
          <button type="submit" data-testid={`${testId}-submit`} disabled={!ready || busy} className="btn btn-primary">
            {busy ? "Delegating…" : "Run specialists"}
            <HoverArrow />
          </button>
        </form>
        {error && (
          <p className="banner-error mt-3" role="alert" data-testid="agent-error">
            {error}
          </p>
        )}
        <div className="a2ui-surface mt-5" data-testid="a2ui-surface">
          <CopilotChatMessageView messages={messages as never} isRunning={busy} data-testid="agent-reply" />
        </div>
      </div>
      <DelegationPanel delegation={delegation} todos={todos} busy={busy} />
    </div>
  );
}
