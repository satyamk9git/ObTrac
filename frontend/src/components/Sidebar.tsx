"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  Home,
  FileText,
  Cpu,
  Layers,
  Database,
  FolderOpen,
  Terminal,
  Bell,
  LayoutDashboard,
  Waypoints,
  BarChart3,
  TrendingUp,
  Columns2,
  MessagesSquare,
  Wallet,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useSidebarCollapsed } from "@/lib/use-sidebar-collapsed";

// Nav definitions ----------------------------------------------------------
type NavItem = {
  name: string;
  href: string;
  icon: React.ElementType;
  badge?: string;
};

const workspaceNav: NavItem[] = [
  { name: "Projects", href: "/", icon: Home },
  { name: "Prompts", href: "/prompts", icon: FileText },
  { name: "LLM Config", href: "/llm-config", icon: Cpu },
  { name: "Embedder Config", href: "/embedder", icon: Layers },
  { name: "DB Config", href: "/db-config", icon: Database, badge: "Soon" },
  { name: "Resources", href: "/resources", icon: FolderOpen },
  { name: "SQL Editor", href: "/sql-editor", icon: Terminal },
  { name: "Alerts", href: "/alerts", icon: Bell },
];

const projectNav: NavItem[] = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Traces", href: "/traces", icon: Waypoints },
  { name: "Metrics", href: "/metrics", icon: BarChart3 },
  { name: "Analytics", href: "/analytics", icon: TrendingUp },
  { name: "Compare", href: "/compare", icon: Columns2 },
  { name: "Sessions", href: "/sessions", icon: MessagesSquare },
  { name: "Budgets", href: "/budgets", icon: Wallet },
];

const ICON_PROPS = { size: 16, strokeWidth: 1.75 };

// Component ----------------------------------------------------------------
export default function Sidebar({ project }: { project?: string }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useSidebarCollapsed();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(href + "/");
  };

  return (
    <TooltipProvider delayDuration={200}>
      <div
        className={`${collapsed ? "w-[68px]" : "w-60"} bg-white border-r border-gray-200 flex flex-col h-screen fixed left-0 top-0 z-40 transition-[width] duration-200`}
      >
        {/* Logo */}
        <Link href="/" className="p-5 border-b border-gray-200 hover:bg-gray-50 transition-colors">
          <div className={`flex items-center gap-2.5 ${collapsed ? "justify-center" : ""}`}>
            <div className="w-10 h-10 rounded-full bg-white border border-gray-200 flex items-center justify-center overflow-hidden shrink-0">
              <Image
                src="/cortexa_logo.png"
                alt="Cortexa"
                width={40}
                height={40}
                className="object-contain p-0.5"
                priority
              />
            </div>
            {!collapsed && (
              <div>
                <h1 className="text-base font-bold text-gray-900 tracking-tight">Cortexa</h1>
                <p className="text-[10px] text-gray-400 -mt-0.5">RAG Observability &amp; Evals</p>
              </div>
            )}
          </div>
        </Link>

        {/* Nav */}
        <nav className="flex-1 px-3 py-3 overflow-y-auto">
          {/* WORKSPACE section ---------------------------------------------- */}
          <div className={`rounded-lg bg-muted/40 pb-2 mb-4 ${collapsed ? "px-0" : "px-0"}`}>
            {!collapsed && (
              <div className="px-3 pt-2 pb-2">
                <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Workspace</p>
              </div>
            )}
            <div className={`space-y-0.5 ${collapsed ? "pt-2" : ""} px-1.5`}>
              {workspaceNav.map((item) => {
                const active = isActive(item.href);
                const link = (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all ${
                      collapsed ? "justify-center" : ""
                    } ${
                      active
                        ? "bg-indigo-50 text-indigo-700 font-medium"
                        : "text-muted-foreground hover:bg-gray-100 hover:text-gray-900"
                    }`}
                  >
                    <item.icon {...ICON_PROPS} className={active ? "text-indigo-600 shrink-0" : "text-gray-400 shrink-0"} />
                    {!collapsed && (
                      <>
                        <span className="flex-1">{item.name}</span>
                        {item.badge && (
                          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                            {item.badge}
                          </span>
                        )}
                      </>
                    )}
                  </Link>
                );
                return collapsed ? (
                  <Tooltip key={item.href}>
                    <TooltipTrigger asChild>{link}</TooltipTrigger>
                    <TooltipContent side="right">{item.name}</TooltipContent>
                  </Tooltip>
                ) : (
                  link
                );
              })}
            </div>
          </div>

          {/* PROJECT section ------------------------------------------------ */}
          {!collapsed && (
            <div className="mb-1 px-3 pt-2 pb-2 border-t border-gray-100">
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mt-3">Project</p>
              {project ? (
                <div className="mt-1.5 border-l-2 border-primary pl-2">
                  <Link href="/" className="text-[10px] text-gray-400 hover:text-gray-600 inline-flex items-center gap-0.5">
                    <ChevronLeft size={12} />
                    <span>All Projects</span>
                  </Link>
                  <p className="text-sm font-semibold text-indigo-600 mt-0.5 truncate" title={project}>
                    {project}
                  </p>
                </div>
              ) : (
                <p className="text-[10px] text-gray-400 mt-1 leading-relaxed">
                  Select a project from the home page to access these tools.
                </p>
              )}
            </div>
          )}
          <div className="space-y-0.5">
            {projectNav.map((item) => {
              const active = !!project && isActive(item.href);
              const disabled = !project;
              const href = project ? `${item.href}?project=${encodeURIComponent(project)}` : "/";
              const link = (
                <Link
                  key={item.href}
                  href={href}
                  aria-disabled={disabled}
                  tabIndex={disabled ? -1 : undefined}
                  onClick={(e) => {
                    if (disabled) e.preventDefault();
                  }}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all ${
                    collapsed ? "justify-center" : ""
                  } ${
                    active
                      ? "bg-indigo-50 text-indigo-700 font-medium"
                      : disabled
                        ? "text-gray-300 cursor-not-allowed"
                        : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                  }`}
                >
                  <item.icon
                    {...ICON_PROPS}
                    className={`shrink-0 ${active ? "text-indigo-600" : disabled ? "text-gray-300" : "text-gray-400"}`}
                  />
                  {!collapsed && item.name}
                </Link>
              );
              return collapsed ? (
                <Tooltip key={item.href}>
                  <TooltipTrigger asChild>{link}</TooltipTrigger>
                  <TooltipContent side="right">{item.name}</TooltipContent>
                </Tooltip>
              ) : (
                link
              );
            })}
          </div>
        </nav>

        {/* Footer */}
        <div className="px-3 py-3 border-t border-gray-200">
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            {!collapsed && <span className="text-[10px]">Collapse</span>}
          </button>
          {!collapsed && (
            <div className="mt-2 text-[10px] text-gray-400 flex items-center justify-center gap-1.5">
              <span>v0.6.8</span>
              <span className="text-gray-300">•</span>
              <span>Open Source</span>
            </div>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}
