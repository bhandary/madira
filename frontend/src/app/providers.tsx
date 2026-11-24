"use client";

import { useEffect } from "react";
import { CopilotKit } from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { beverageCatalog } from "@/a2ui/catalog";
import { registerServiceWorker } from "@/lib/offline";
import "./copilot-overrides.css";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    registerServiceWorker();
  }, []);
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="head_sommelier"
      enableInspector={false}
      a2ui={{
        theme: {
          colors: { primary: "#533afd" },
        },
        catalog: beverageCatalog,
      }}
    >
      {children}
    </CopilotKit>
  );
}
