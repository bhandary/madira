"use client";

import { useEffect } from "react";
import { CopilotKit } from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { beverageCatalog } from "@/a2ui/catalog";
import { CSRF_HEADER, ensureCsrfToken } from "@/lib/csrf";
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
      credentials="same-origin"
      headers={async () => {
        const token = await ensureCsrfToken();
        return token ? { [CSRF_HEADER]: token } : {};
      }}
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
