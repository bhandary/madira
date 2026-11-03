"use client";

import { useEffect, useState } from "react";
import { AgentWorkbench } from "@/components/AgentWorkbench";
import { getSampleMenu } from "@/lib/api";

export default function MenuPage() {
  const [sample, setSample] = useState(
    "MAISON MADIRA — Autumn Tasting Menu\n1. Dungeness crab, yuzu, avocado, cucumber — $24"
  );
  const [fileName, setFileName] = useState("");

  useEffect(() => {
    getSampleMenu()
      .then((d) => setSample(d.text))
      .catch(() => undefined);
  }, []);

  const prompt = `Parse this menu (PDF/image/text) and recommend wine, beer, spirit, and sake pairings for each dish with a flavor-profile rationale and price-tier fit.\n\n${sample}`;

  return (
    <AgentWorkbench
      testId="menu-workbench"
      title="Menu & pairings"
      blurb="Upload a PDF, an image, or paste text. Menu Analyst parses dishes; Pairing Sommelier renders A2UI pairing cards."
      prompt={prompt}
    >
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="text-sm">
          Upload PDF, image, or text
          <input
            data-testid="menu-file"
            type="file"
            accept=".pdf,image/*,.txt"
            className="ml-2 text-sm"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setFileName(file.name);
              if (file.type.startsWith("image/") || file.name.toLowerCase().endsWith(".pdf")) {
                setSample(
                  `${sample}\n\n[Attached ${file.name} — demo mode uses the Maison Madira tasting menu fixture.]`
                );
                return;
              }
              const text = await file.text();
              setSample(text);
            }}
          />
        </label>
        {fileName && (
          <span className="text-xs" data-testid="menu-filename">
            {fileName}
          </span>
        )}
      </div>
    </AgentWorkbench>
  );
}
