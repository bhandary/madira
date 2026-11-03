import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
  InMemoryAgentRunner,
} from "@copilotkit/runtime/v2";

const backend = process.env.MADIRA_BACKEND_URL || "http://127.0.0.1:8123";

const runtime = new CopilotRuntime({
  agents: {
    // @ag-ui/client is installed twice (app 1.0.3, CopilotKit runtime 1.0.2), so
    // the classes are nominally distinct. The instance is the runtime's HttpAgent.
    head_sommelier: new HttpAgent({
      url: `${backend}/ag-ui`,
    }) as never,
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
