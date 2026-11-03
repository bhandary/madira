"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getStatus } from "@/lib/api";

const NAV = [
  { href: "/", label: "Floor" },
  { href: "/menu", label: "Menu & pairings" },
  { href: "/list", label: "List curation" },
  { href: "/inventory", label: "Inventory" },
  { href: "/training", label: "Staff training" },
  { href: "/suppliers", label: "Supplier tastings" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [status, setStatus] = useState<{ demo_mode?: boolean; label?: string; llm_model?: string } | null>(null);

  useEffect(() => {
    getStatus()
      .then(setStatus)
      .catch(() => setStatus({ demo_mode: true, label: "DEMO MODE — backend starting" }));
  }, []);

  return (
    <div className="min-h-screen">
      <div className="bg-burgundy text-cream">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link href="/" className="font-serif text-2xl tracking-tight">
            Madira
          </Link>
          <p className="text-sm text-gold-soft">Maison Madira · beverage program</p>
          <span className="demo-ribbon rounded-full bg-gold/20 px-3 py-1 text-[10px]" data-testid="mode-banner">
            {status?.demo_mode ? "DEMO MODE" : "LIVE"} · {status?.label || "connecting"}
          </span>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-2 pb-2">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap rounded-full px-3 py-1.5 text-sm ${
                  active ? "bg-cream text-burgundy" : "text-cream/80 hover:bg-white/10"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
