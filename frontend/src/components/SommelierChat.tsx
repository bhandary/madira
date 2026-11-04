"use client";

import { useEffect, useState } from "react";
import { CopilotChat, useAgent } from "@copilotkit/react-core/v2";

export function SommelierChat() {
  const { agent } = useAgent();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const subscription = agent.subscribe({
      onRunStartedEvent: () => setError(null),
    });
    return () => subscription.unsubscribe();
  }, [agent]);

  return (
    <div
      className="flex h-[480px] flex-col overflow-hidden rounded-2xl border border-gold/40 bg-white/80"
      data-testid="copilot-chat"
    >
      {error ? (
        <p
          className="shrink-0 border-b border-[#e7cfc6] bg-[#f8e8e4] px-3 py-2 text-sm text-[#a33b24]"
          role="alert"
          data-testid="copilot-chat-error"
        >
          {error}
        </p>
      ) : null}
      <CopilotChat
        className="min-h-0 flex-1"
        onError={(event) => {
          if (!("error" in event) || !(event.error instanceof Error)) return;
          const message = event.error.message.trim();
          setError(message || "The sommelier could not answer.");
        }}
      />
    </div>
  );
}
