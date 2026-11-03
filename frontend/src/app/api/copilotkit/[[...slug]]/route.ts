import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
  InMemoryAgentRunner,
} from "@copilotkit/runtime/v2";

const backend = process.env.MADIRA_BACKEND_URL || "http://127.0.0.1:8123";

const runtime = new CopilotRuntime({
  agents: {
    head_sommelier: new HttpAgent({
      url: `${backend}/ag-ui`,
    }),
  },
  a2ui: { enabled: true },
  runner: new InMemoryAgentRunner(),
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
