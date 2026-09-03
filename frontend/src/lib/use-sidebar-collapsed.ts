"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "cortexa:sidebar-collapsed";

/**
 * Shared collapsed/expanded state for the sidebar, persisted in
 * localStorage so it survives navigation and reloads. Both Sidebar and
 * the project layout (which needs to know the width to offset main
 * content) read this same hook rather than prop-drilling across the
 * Suspense boundary between them.
 */
export function useSidebarCollapsed(): [boolean, (next: boolean) => void] {
  const [collapsed, setCollapsedState] = useState(false);

  useEffect(() => {
    try {
      setCollapsedState(localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      // localStorage unavailable (e.g. private mode) — stay expanded
    }
  }, []);

  const setCollapsed = (next: boolean) => {
    setCollapsedState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      // ignore write failures
    }
    window.dispatchEvent(new CustomEvent("cortexa:sidebar-collapsed-change", { detail: next }));
  };

  // Stay in sync if another component (or another tab) changes it.
  useEffect(() => {
    const onCustom = (e: Event) => setCollapsedState((e as CustomEvent<boolean>).detail);
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setCollapsedState(e.newValue === "1");
    };
    window.addEventListener("cortexa:sidebar-collapsed-change", onCustom);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("cortexa:sidebar-collapsed-change", onCustom);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return [collapsed, setCollapsed];
}
