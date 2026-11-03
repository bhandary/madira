"use client";

import { CopilotChat } from "@copilotkit/react-core/v2";

export function SommelierChat() {
  return (
    <div className="h-[480px] overflow-hidden rounded-2xl border border-gold/40 bg-white/80" data-testid="copilot-chat">
      <CopilotChat className="h-full" />
    </div>
  );
}
