"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { AccountMenu, useAccount } from "@/components/AccountMenu";
import { TabletChrome } from "@/components/TabletMode";
import { getDemoPersonas, getStatus, getTablet, getTonight } from "@/lib/api";

const SIDEBAR = [
  { href: "/", label: "Tonight" },
  { href: "/lookup", label: "Lookup" },
  { href: "/menu", label: "Menu & pairings" },
  { href: "/list", label: "List curation" },
  { href: "/inventory", label: "Inventory" },
  { href: "/purchasing", label: "Purchasing" },
  { href: "/inventory/count", label: "Phone count" },
  { href: "/training", label: "Staff training" },
  { href: "/suppliers", label: "Suppliers" },
  { href: "/tastings", label: "Tastings" },
  { href: "/sourcing", label: "Sourcing" },
  { href: "/pos", label: "POS" },
  { href: "/sensors", label: "Sensors" },
  { href: "/audit", label: "Audit" },
  { href: "/usage", label: "Usage" },
  { href: "/records", label: "Records" },
  { href: "/settings", label: "Settings" },
];

const TABS = [
  { href: "/", label: "Tonight", icon: "floor" },
  { href: "/menu", label: "Menu", icon: "menu" },
  { href: "/inventory", label: "Cellar", icon: "cellar" },
  { href: "/list", label: "List", icon: "list" },
  { href: "/training", label: "Team", icon: "team" },
] as const;

const STAFF_SIDEBAR = [
  { href: "/", label: "Tonight" },
  { href: "/lookup", label: "Lookup" },
  { href: "/training", label: "Lessons" },
];

const STAFF_TABS = [
  { href: "/", label: "Tonight", icon: "floor" },
  { href: "/lookup", label: "Lookup", icon: "lookup" },
  { href: "/training", label: "Lessons", icon: "team" },
] as const;

const MORE = [
  { href: "/suppliers", label: "Suppliers" },
  { href: "/tastings", label: "Tastings" },
  { href: "/sourcing", label: "Sourcing" },
  { href: "/pos", label: "POS" },
  { href: "/sensors", label: "Sensors" },
  { href: "/audit", label: "Audit" },
  { href: "/usage", label: "Usage" },
  { href: "/records", label: "Records" },
  { href: "/settings", label: "Settings" },
];

const STAFF_PATHS = new Set(["/", "/lookup", "/training", "/login"]);

function Brand() {
  return (
    <Link href="/" className="brand">
      <span className="brand-mark" aria-hidden="true">
        M
      </span>
      Madira
    </Link>
  );
}

function TabIcon({ name }: { name: (typeof TABS)[number]["icon"] | (typeof STAFF_TABS)[number]["icon"] | "more" }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (name === "floor") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M6 7.5h12v8.2a2 2 0 0 1-2 2H9.2L6 20.2V7.5Z" />
      </svg>
    );
  }
  if (name === "menu") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M7 6.5h10M7 12h10M7 17.5h6" />
      </svg>
    );
  }
  if (name === "cellar") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M9 4.5h6v3.2c1.8.7 3 2.3 3 4.3v7H6v-7c0-2 1.2-3.6 3-4.3V4.5Z" />
        <path {...common} d="M9 4.5h6M8 15.5h8" />
      </svg>
    );
  }
  if (name === "list") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M8 5.5h10v14H8a2 2 0 0 1-2-2v-10a2 2 0 0 1 2-2Z" />
        <path {...common} d="M10 10h6M10 13.5h6M10 17h4" />
      </svg>
    );
  }
  if (name === "lookup") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M11 16.5a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11Z" />
        <path {...common} d="M15.2 15.2 19 19" />
      </svg>
    );
  }
  if (name === "team") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path {...common} d="M8.5 11a2.4 2.4 0 1 0 0-4.8 2.4 2.4 0 0 0 0 4.8ZM15.8 11.2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />
        <path {...common} d="M4.8 18.2c.5-2.2 2.1-3.4 3.7-3.4s3.2 1.2 3.7 3.4M13.2 15c1.3-.3 2.6.2 3.4 1.4.6.9 1 1.8 1.2 2.8" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...common} d="M6.5 12h.01M12 12h.01M17.5 12h.01" />
      <path {...common} d="M6.5 12a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8ZM12 12a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8ZM17.5 12a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8Z" />
    </svg>
  );
}

function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const sync = () => setOffline(!navigator.onLine);
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, []);
  if (!offline) return null;
  return (
    <div className="announce" role="status" data-testid="offline-banner">
      <span className="min-w-0">Offline. Tonight, lookup, and open counts stay on this phone.</span>
    </div>
  );
}

function modeDetail(label: string) {
  return label.replace(/^(?:DEMO MODE|LIVE)\s*(?:—|-)\s*/i, "");
}

function ModeBanner({ status }: { status: { demo_mode?: boolean; label?: string } | null }) {
  const demo = status?.demo_mode !== false;
  const detail = modeDetail(status?.label || "connecting");
  return (
    <div className="announce sticky top-0 z-30" data-testid="mode-banner">
      <span className={demo ? "mode-dot" : "mode-dot mode-dot-live"} aria-hidden="true" />
      <span className="min-w-0">
        <span className="mode-word">{status?.demo_mode === false ? "LIVE" : "DEMO MODE"}</span>
        <span className="mode-detail">{detail}</span>
      </span>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const moreId = useId();
  const moreButton = useRef<HTMLButtonElement>(null);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const moreOpen = openPath === pathname;
  const [status, setStatus] = useState<{ demo_mode?: boolean; label?: string; llm_model?: string } | null>(null);
  const statusTicket = useRef(0);
  const [role, setRole] = useState<string | null>(null);
  const { user, signOut } = useAccount();
  const staff = role === "Staff";
  const sidebar = staff ? STAFF_SIDEBAR : SIDEBAR;
  const tabs = staff ? STAFF_TABS : TABS;
  const moreCurrent =
    pathname === "/suppliers" ||
    pathname === "/tastings" ||
    pathname === "/sourcing" ||
    pathname === "/pos" ||
    pathname === "/sensors" ||
    pathname === "/audit" ||
    pathname === "/usage" ||
    pathname === "/records" ||
    pathname === "/settings" ||
    pathname === "/login";
  const bare = pathname.startsWith("/l/");

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      if (bare) return;
      const ticket = ++statusTicket.current;
      getStatus()
        .then((next) => {
          if (cancelled || ticket !== statusTicket.current) return;
          setStatus(next);
        })
        .catch(() => {
          if (cancelled || ticket !== statusTicket.current) return;
          setStatus({ demo_mode: true, label: "DEMO MODE — backend starting" });
        });
    };
    load();
    window.addEventListener("madira-status", load);
    return () => {
      cancelled = true;
      window.removeEventListener("madira-status", load);
    };
  }, [pathname, bare]);

  useEffect(() => {
    if (bare) return;
    let cancelled = false;
    getTablet()
      .then(async (tablet) => {
        if (cancelled) return;
        if (tablet.actor) {
          setRole(tablet.actor.role);
          return;
        }
        const payload = await getDemoPersonas();
        if (cancelled) return;
        if (payload) {
          const active = payload.personas.find((persona) => persona.slug === payload.active);
          setRole(active?.role || "Owner");
          return;
        }
        try {
          const board = await getTonight();
          if (!cancelled) setRole(board.role || "");
        } catch {
          if (!cancelled) setRole("");
        }
      })
      .catch(() => {
        if (!cancelled) setRole("");
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, bare]);

  useEffect(() => {
    if (bare || role !== "Staff" || STAFF_PATHS.has(pathname)) return;
    router.replace("/");
  }, [bare, role, pathname, router]);

  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenPath(null);
        moreButton.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [moreOpen]);

  if (bare) return <>{children}</>;

  return (
    <div className="min-h-dvh bg-canvas md:flex">
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <aside className="sidebar hidden w-60 shrink-0 md:block">
        <div className="sidebar-scroll">
          <div className="px-4 pb-4 pt-5">
            <Brand />
            <p className="mt-2 text-xs leading-5 text-muted">Maison Madira</p>
            <p className="text-xs leading-5 text-muted">Beverage program</p>
          </div>
          <nav id="app-nav" className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-3" aria-label="Sections">
            {sidebar.map((item) => {
              const active = pathname === item.href;
              return (
                <Link key={item.href} href={item.href} className="nav-link" aria-current={active ? "page" : undefined}>
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="px-2 pb-4">
            <AccountMenu user={user} onSignOut={() => void signOut()} />
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <ModeBanner status={status} />
        <TabletChrome pathname={pathname} onRole={setRole} />
        <OfflineBanner />
        <header className="flex items-center border-b border-line bg-panel px-4 py-3 md:hidden">
          <Brand />
        </header>
        <main id="content" className="shell-main">
          {children}
        </main>
      </div>
      <nav className="tabbar md:hidden" aria-label="Sections" data-testid="phone-tabs">
        {tabs.map((item) => {
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href} className="tab" aria-current={active ? "page" : undefined}>
              <TabIcon name={item.icon} />
              {item.label}
            </Link>
          );
        })}
        {staff ? null : (
          <button
            ref={moreButton}
            type="button"
            className="tab"
            aria-expanded={moreOpen}
            aria-controls={moreId}
            aria-current={moreCurrent && !moreOpen ? "page" : undefined}
            onClick={() => setOpenPath(moreOpen ? null : pathname)}
          >
            <TabIcon name="more" />
            More
          </button>
        )}
      </nav>
      {moreOpen && !staff ? (
        <>
          <div className="more-backdrop md:hidden" onClick={() => setOpenPath(null)} />
          <div id={moreId} className="more-sheet md:hidden" data-testid="mobile-menu">
            <nav className="flex flex-col gap-0.5" aria-label="More">
              {MORE.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link key={item.href} href={item.href} className="nav-link" aria-current={active ? "page" : undefined}>
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <AccountMenu user={user} onSignOut={() => void signOut()} />
          </div>
        </>
      ) : null}
    </div>
  );
}
