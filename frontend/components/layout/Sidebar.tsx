"use client";

import { ChevronLeft, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandMark } from "@/components/icons";
import { navItems } from "@/components/layout/nav";
import { cn } from "@/lib/utils";
import { siteConfig } from "@/lib/site";

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggleCollapse: () => void;
  onCloseMobile: () => void;
}

export function Sidebar({
  collapsed,
  mobileOpen,
  onToggleCollapse,
  onCloseMobile,
}: SidebarProps) {
  const pathname = usePathname();

  const nav = (
    <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Primary">
      <ul className="space-y-1">
        {navItems.map((item) => {
          const active = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href);
          const Icon = item.icon;

          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                  active
                    ? "bg-primary/10 text-ink"
                    : "text-muted hover:bg-surface-raised/60 hover:text-ink",
                )}
              >
                <span
                  className={cn(
                    "grid size-7 shrink-0 place-items-center rounded-md",
                    active ? "text-primary" : "text-muted group-hover:text-ink",
                  )}
                  aria-hidden
                >
                  <Icon className="size-4" />
                </span>
                {!collapsed && (
                  <span className="truncate font-medium">{item.label}</span>
                )}
                {active && !collapsed && (
                  <span
                    className="ml-auto size-1.5 rounded-full bg-primary"
                    aria-hidden
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );

  const brand = (
    <div className="flex items-center gap-3 border-b border-line/60 px-4 py-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
        <BrandMark className="size-5" />
      </span>
      {!collapsed && (
        <div className="min-w-0">
          <p className="truncate text-sm font-medium tracking-[-0.01em] text-ink">
            {siteConfig.name}
          </p>
          <p className="truncate font-mono text-[9px] uppercase tracking-[0.14em] text-muted/70">
            Energy intelligence
          </p>
        </div>
      )}
    </div>
  );

  const footer = (
    <div className="border-t border-line/60 px-4 py-3">
      <p
        className={cn(
          "font-mono text-[9px] uppercase tracking-[0.12em] text-muted/60",
          collapsed && "hidden",
        )}
      >
        Local · Phase 6
      </p>
    </div>
  );

  return (
    <>
      {/* Desktop rail */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-line bg-surface/80 backdrop-blur lg:flex",
          "transition-[width] duration-200",
          collapsed ? "w-[72px]" : "w-[240px]",
        )}
      >
        {brand}
        {nav}
        <div className="border-t border-line/60 px-3 py-3">
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[11px] text-muted transition-colors",
              "hover:bg-surface-raised/60 hover:text-ink",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
              collapsed && "justify-center px-0",
            )}
          >
            <ChevronLeft
              className={cn("size-4 transition-transform", collapsed && "rotate-180")}
              aria-hidden
            />
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
        {footer}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={onCloseMobile}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col border-r border-line bg-surface lg:hidden",
          "transition-transform duration-200",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-hidden={!mobileOpen}
      >
        <div className="relative">
          <button
            type="button"
            onClick={onCloseMobile}
            aria-label="Close navigation"
            className="absolute right-3 top-4 grid size-8 place-items-center rounded-md text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <X className="size-4" />
          </button>
          {brand}
        </div>
        {nav}
        {footer}
      </aside>
    </>
  );
}
