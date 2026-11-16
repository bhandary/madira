import { EventType, HttpAgent, type BaseEvent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
  InMemoryAgentRunner,
  type AgentRunnerConnectRequest,
} from "@copilotkit/runtime/v2";
import { Observable } from "rxjs";

const backend = process.env.MADIRA_BACKEND_URL || "http://127.0.0.1:8123";

class CheckpointAgentRunner extends InMemoryAgentRunner {
  override connect(request: AgentRunnerConnectRequest): Observable<BaseEvent> {
    const scope = request.ownerId !== undefined ? { ownerId: request.ownerId } : undefined;
    if (this.getThreadMessages(request.threadId, scope).length > 0) {
      return super.connect(request);
    }
    return new Observable<BaseEvent>((subscriber) => {
      let closed = false;
      hydrateThread(request.threadId, request.headers)
        .then((messages) => {
          if (closed) return;
          if (messages.length === 0) {
            subscriber.complete();
            return;
          }
          const runId = crypto.randomUUID();
          subscriber.next({ type: EventType.RUN_STARTED, threadId: request.threadId, runId });
          subscriber.next({ type: EventType.MESSAGES_SNAPSHOT, messages, runId });
          subscriber.next({ type: EventType.RUN_FINISHED, threadId: request.threadId, runId });
          subscriber.complete();
        })
        .catch(() => {
          if (!closed) subscriber.complete();
        });
      return () => {
        closed = true;
      };
    });
  }
}

async function hydrateThread(threadId: string, headers?: Record<string, string>) {
  const forwarded: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers ?? {})) {
    const name = key.toLowerCase();
    if ((name === "cookie" || name === "authorization") && value) forwarded[name] = value;
  }
  const res = await fetch(`${backend}/ag-ui/threads/${encodeURIComponent(threadId)}/messages`, {
    headers: forwarded,
    cache: "no-store",
  });
  if (!res.ok) return [];
  const body = (await res.json()) as { messages?: unknown };
  return Array.isArray(body.messages) ? body.messages : [];
}

const runtime = new CopilotRuntime({
  agents: {
    // @ag-ui/client is installed twice (app 1.0.3, CopilotKit runtime 1.0.2), so
    // the classes are nominally distinct. The instance is the runtime's HttpAgent.
    head_sommelier: new HttpAgent({
      url: `${backend}/ag-ui`,
    }) as never,
  },
  a2ui: { enabled: true },
  // Cookie reaches the backend so the checkpointer scopes the thread to this venue.
  forwardHeaders: { allow: ["cookie", "authorization"] },
  runner: new CheckpointAgentRunner(),
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
});

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const OPTIONS = handler;
