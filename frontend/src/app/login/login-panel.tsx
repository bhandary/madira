"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AccountMenu, useAccount } from "@/components/AccountMenu";
import { getAuthConfig } from "@/lib/api";

const ERRORS: Record<string, string> = {
  denied: "Google sign-in was cancelled.",
  state: "That sign-in attempt expired. Try again.",
  token: "Google did not complete sign-in. Try again.",
  id_token: "The Google ID token could not be verified.",
  not_configured: "Google sign-in isn't configured.",
  server: "Sign-in failed. Try again.",
};

function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
      />
    </svg>
  );
}

export function LoginPanel({ error }: { error: string }) {
  const { user, signOut } = useAccount();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const message = ERRORS[error] ?? (error ? "Sign-in failed. Try again." : "");

  useEffect(() => {
    let cancelled = false;
    getAuthConfig()
      .then((data) => {
        if (!cancelled) setConfigured(data.configured);
      })
      .catch(() => {
        if (!cancelled) setUnreachable(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const waiting = user === undefined || (user === null && configured === null && !unreachable);

  return (
    <div className="mt-6 space-y-4">
      {message ? (
        <p className="banner-error" role="alert" data-testid="login-error">
          {message}
        </p>
      ) : null}
      {user ? (
        <div className="panel px-3 py-2">
          <AccountMenu user={user} onSignOut={() => void signOut()} />
          <p className="px-1 pb-2 text-sm text-muted">
            <Link href="/" className="underline-offset-2 hover:underline">
              Back to the floor
            </Link>
          </p>
        </div>
      ) : null}
      {waiting ? (
        <p className="text-sm text-muted">Checking sign-in…</p>
      ) : user ? null : unreachable ? (
        <p className="banner-error" role="alert" data-testid="login-unavailable">
          Couldn&apos;t reach the sign-in service.
        </p>
      ) : configured ? (
        <div className="panel p-4">
          <a href="/madira-api/auth/google" className="btn btn-secondary w-full gap-2" data-testid="google-sign-in">
            <GoogleMark />
            Continue with Google
          </a>
        </div>
      ) : (
        <p className="panel px-3 py-3 text-sm leading-6 text-muted" data-testid="login-unconfigured">
          Google sign-in isn&apos;t configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, MADIRA_AUTH_SECRET, and
          MADIRA_PUBLIC_URL on the backend, then restart it.
        </p>
      )}
    </div>
  );
}
