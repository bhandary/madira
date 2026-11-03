"use client";

import { useState } from "react";
import { AgentWorkbench } from "@/components/AgentWorkbench";

export default function TrainingPage() {
  const [mode, setMode] = useState<"briefing" | "quiz" | "roleplay">("quiz");
  const prompts = {
    briefing: "Deliver today's pairing briefing, wine-knowledge lesson, and service etiquette for waitstaff and bartenders.",
    quiz: "Grade the floor quiz with answers 1,2,2,1 for staff name Floor.",
    roleplay: "Start diner roleplay. Play a skeptical guest who ordered the dry-aged ribeye.",
  };

  return (
    <AgentWorkbench
      testId="training-workbench"
      title="Staff training"
      blurb="Lessons, tonight's pairing briefing, a scored quiz, and a diner roleplay. Staff Trainer owns the floor notebook."
      prompt={prompts[mode]}
    >
      <div className="mt-4 flex flex-wrap gap-2">
        {(["briefing", "quiz", "roleplay"] as const).map((key) => (
          <button
            key={key}
            type="button"
            data-testid={`training-${key}`}
            onClick={() => {
              setMode(key);
              const el = document.getElementById("training-workbench-prompt") as HTMLTextAreaElement;
              if (el) {
                el.value = prompts[key];
                el.dispatchEvent(new Event("input", { bubbles: true }));
              }
            }}
            className={`rounded-full px-3 py-1 text-sm ${
              mode === key ? "bg-burgundy text-cream" : "border border-burgundy"
            }`}
          >
            {key}
          </button>
        ))}
      </div>
    </AgentWorkbench>
  );
}
