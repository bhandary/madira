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
  { href: "/settings", label: "Settings" },
];

function ModeBanner({ status }: { status: { demo_mode?: boolean; label?: string } | null }) {
  const demo = status?.demo_mode !== false;
  const detail = (status?.label || "connecting").replace(/^DEMO MODE\s*[—-]\s*/i, "");
  return (
    <span className="mode-pill" data-testid="mode-banner">
      <span className={demo ? "mode-dot" : "mode-dot mode-dot-live"} aria-hidden="true" />
      <span className="min-w-0">
        <span className="mode-word">{status?.demo_mode === false ? "LIVE" : "DEMO MODE"}</span>
        <span className="mode-detail">{detail}</span>
      </span>
    </span>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === pathname;
  const [status, setStatus] = useState<{ demo_mode?: boolean; label?: string; llm_model?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      getStatus()
        .then((next) => {
          if (!cancelled) setStatus(next);
        })
        .catch(() => {
          if (!cancelled) setStatus({ demo_mode: true, label: "DEMO MODE — backend starting" });
        });
    };
    load();
    window.addEventListener("madira-status", load);
    return () => {
      cancelled = true;
      window.removeEventListener("madira-status", load);
    };
  }, [pathname]);

  const links = (id: string) => (
    <nav id={id} className="flex flex-col gap-0.5" aria-label="Sections">
      {NAV.map((item) => {
        const active = pathname === item.href;
        return (
          <Link key={item.href} href={item.href} className="nav-link" aria-current={active ? "page" : undefined}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen bg-canvas">
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <div className="md:flex">
        <aside className="sticky top-0 hidden h-dvh w-56 shrink-0 flex-col border-r border-line bg-panel md:flex">
          <div className="px-3 pb-3 pt-4">
            <Link href="/" className="block text-[15px] font-medium tracking-tight">
              Madira
            </Link>
            <p className="mt-1 text-[11px] leading-4 text-muted">Maison Madira</p>
            <p className="text-[11px] leading-4 text-muted">Beverage program</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">{links("app-nav")}</div>
        </aside>
        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 border-b border-line bg-canvas/95 backdrop-blur">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 md:px-6">
              <button
                type="button"
                className="btn btn-secondary md:hidden"
                aria-expanded={open}
                aria-controls="app-nav-mobile"
                onClick={() => setOpenPath(open ? null : pathname)}
              >
                Sections
              </button>
              <Link href="/" className="text-sm font-medium tracking-tight md:hidden">
                Madira
              </Link>
              <ModeBanner status={status} />
            </div>
            {open ? <div className="border-t border-line px-2 py-2 md:hidden">{links("app-nav-mobile")}</div> : null}
          </header>
          <main id="content" className="mx-auto w-full max-w-6xl px-3 py-5 md:px-6 md:py-6">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
