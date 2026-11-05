"use client";

import { CopilotKit } from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { beverageCatalog } from "@/a2ui/catalog";
import "./copilot-overrides.css";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="head_sommelier"
      a2ui={{
        theme: {
          colors: { primary: "#8d3846" },
        },
        catalog: beverageCatalog,
      }}
    >
      {children}
    </CopilotKit>
  );
}
