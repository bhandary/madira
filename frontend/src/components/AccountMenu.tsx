"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { getAccount, notifyAuthChanged, signOutAccount, type Account } from "@/lib/api";

export function useAccount() {
  const [user, setUser] = useState<Account | null | undefined>(undefined);
  const seq = useRef(0);

  const refresh = useCallback(() => {
    const id = ++seq.current;
    void getAccount().then((next) => {
      if (id === seq.current) setUser(next);
    });
  }, []);

  useEffect(() => {
    refresh();
    const onChange = () => refresh();
    window.addEventListener("madira-auth", onChange);
    return () => window.removeEventListener("madira-auth", onChange);
  }, [refresh]);

  const signOut = useCallback(async () => {
    const id = ++seq.current;
    const ok = await signOutAccount();
    if (!ok) {
      refresh();
      return;
    }
    if (id === seq.current) setUser(null);
    notifyAuthChanged();
  }, [refresh]);

  return { user, signOut };
}

function pictureSrc(picture: string): string {
  try {
    const url = new URL(picture);
    const host = url.hostname.toLowerCase();
    const allowed =
      host === "googleusercontent.com" ||
      host.endsWith(".googleusercontent.com") ||
      host === "ggpht.com" ||
      host.endsWith(".ggpht.com");
    if (url.protocol !== "https:" || !allowed || url.username || url.password) return "";
    return picture;
  } catch {
    return "";
  }
}

function Avatar({ user }: { user: Account }) {
  const [broken, setBroken] = useState(false);
  const src = pictureSrc(user.picture);
  const initial = (user.name || user.email || "?").trim().charAt(0).toUpperCase() || "?";
  if (!src || broken) {
    return (
      <span className="account-avatar" data-testid="account-avatar" aria-hidden="true">
        {initial}
      </span>
    );
  }
  return (
    <Image
      src={src}
      alt=""
      width={28}
      height={28}
      unoptimized
      className="account-avatar"
      data-testid="account-avatar"
      referrerPolicy="no-referrer"
      onError={() => setBroken(true)}
    />
  );
}

export function AccountMenu({
  user,
  onSignOut,
}: {
  user: Account | null | undefined;
  onSignOut: () => void;
}) {
  const pathname = usePathname();
  if (user === undefined) return null;
  if (!user) {
    return (
      <div className="account-block" data-testid="account-menu">
        <Link
          href="/login"
          className="nav-link"
          data-testid="sign-in-link"
          aria-current={pathname === "/login" ? "page" : undefined}
        >
          Sign in
        </Link>
      </div>
    );
  }
  const label = user.name || user.email || "Signed in";
  return (
    <div className="account-block" data-testid="account-menu">
      <div className="flex min-w-0 items-center gap-2">
        <Avatar user={user} />
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium" data-testid="account-name" title={label}>
            {label}
          </p>
          {user.email && user.name ? <p className="truncate text-[11px] text-muted">{user.email}</p> : null}
        </div>
      </div>
      <button type="button" className="btn btn-secondary mt-2 w-full" data-testid="sign-out" onClick={onSignOut}>
        Sign out
      </button>
    </div>
  );
}
