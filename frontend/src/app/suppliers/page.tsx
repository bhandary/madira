"use client";

import { AgentWorkbench } from "@/components/AgentWorkbench";

export default function SuppliersPage() {
  return (
    <AgentWorkbench
      testId="suppliers-workbench"
      title="Supplier tastings"
      blurb="Hold a cellar tasting with an importer or distributor. Madira writes a draft .ics and never sends email or calendar invites."
      prompt="Schedule a tasting with Kermit Lynch Wine Merchant titled New Loire releases tasting at the Maison Madira cellar. Produce a draft .ics only — do not send."
    />
  );
}
