"use client";

import { useSyncExternalStore } from "react";

const ids = new Map<string, string>();

function subscribe(): () => void {
  return () => undefined;
}

function serverThreadId(): null {
  return null;
}

function readThreadId(key: string): string {
  const cached = ids.get(key);
  if (cached) return cached;
  let created: string;
  try {
    const existing = localStorage.getItem(key);
    if (existing) created = existing;
    else {
      created = crypto.randomUUID();
      localStorage.setItem(key, created);
    }
  } catch {
    created = crypto.randomUUID();
  }
  ids.set(key, created);
  return created;
}

export function useStoredThreadId(key: string): string | null {
  return useSyncExternalStore(subscribe, () => readThreadId(key), serverThreadId);
}
