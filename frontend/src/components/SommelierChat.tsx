"use client";

import { useEffect, useState } from "react";
import { CopilotChat, useAgent } from "@copilotkit/react-core/v2";
import { useStoredThreadId } from "@/lib/thread";

export function SommelierChat() {
  const { agent } = useAgent();
  const [error, setError] = useState<string | null>(null);
  const threadId = useStoredThreadId("madira-thread:floor");

  useEffect(() => {
    const subscription = agent.subscribe({
      onRunStartedEvent: () => setError(null),
    });
    return () => subscription.unsubscribe();
  }, [agent]);

  return (
    <div className="sommelier-chat panel flex h-[min(32rem,70dvh)] flex-col overflow-hidden md:h-[32rem]" data-testid="copilot-chat">
      {error ? (
        <p className="banner-error shrink-0 rounded-none border-x-0 border-t-0" role="alert" data-testid="copilot-chat-error">
          {error}
        </p>
      ) : null}
      {threadId ? (
        <CopilotChat
          threadId={threadId}
          className="min-h-0 flex-1"
          onError={(event) => {
            if (!("error" in event) || !(event.error instanceof Error)) return;
            const message = event.error.message.trim();
            setError(message || "The sommelier could not answer.");
          }}
        />
      ) : null}
    </div>
  );
}
