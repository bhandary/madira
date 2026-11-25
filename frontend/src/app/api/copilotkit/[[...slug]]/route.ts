import { CSRF_BLOCKED, csrfBlock } from "@/lib/csrf";
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
  forwardHeaders: { allow: ["cookie", "authorization", "x-csrf-token", "origin"] },
  runner: new CheckpointAgentRunner(),
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
});

type RouteContext = { params: Promise<{ slug?: string[] }> };

function protect(method: string, inner: (request: Request, context: RouteContext) => Promise<Response> | Response) {
  return async (request: Request, context: RouteContext) => {
    if (method !== "GET" && method !== "OPTIONS" && method !== "HEAD") {
      const host = (request.headers.get("x-forwarded-host") || request.headers.get("host") || "").split(",")[0].trim();
      const proto = (request.headers.get("x-forwarded-proto") || new URL(request.url).protocol.replace(":", "")).split(",")[0].trim();
      const reason = csrfBlock(request, host && proto ? `${proto}://${host}` : "");
      if (reason) {
        console.warn("csrf rejected method=%s path=%s reason=%s", request.method, new URL(request.url).pathname, reason);
        return Response.json({ detail: CSRF_BLOCKED }, { status: 403 });
      }
    }
    return inner(request, context);
  };
}

export const GET = protect("GET", handler);
export const POST = protect("POST", handler);
export const PUT = protect("PUT", handler);
export const PATCH = protect("PATCH", handler);
export const DELETE = protect("DELETE", handler);
export const OPTIONS = protect("OPTIONS", handler);
