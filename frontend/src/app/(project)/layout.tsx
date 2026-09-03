"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Sidebar from "@/components/Sidebar";
import SearchBar from "@/components/SearchBar";
import RunningEvalsBadge from "@/components/RunningEvalsBadge";
import { useSidebarCollapsed } from "@/lib/use-sidebar-collapsed";

function ProjectLayoutInner({ children }: { children: React.ReactNode }) {
  const searchParams = useSearchParams();
  const project = searchParams.get("project") || undefined;
  const [collapsed] = useSidebarCollapsed();

  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar project={project} />
      <main className={`flex-1 transition-[margin] duration-200 ${collapsed ? "ml-[68px]" : "ml-60"}`}>
        {/* Top bar */}
        <div className="sticky top-0 z-20 bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-end gap-3">
          <RunningEvalsBadge />
          <SearchBar project={project} />
        </div>
        <div className="p-6 animate-fade-in">
          {children}
        </div>
      </main>
    </div>
  );
}

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen text-gray-500">Loading...</div>}>
      <ProjectLayoutInner>{children}</ProjectLayoutInner>
    </Suspense>
  );
}
