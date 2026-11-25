"use client";

import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { cn } from "@/lib/utils";

/**
 * Persistent application shell: sidebar navigation, sticky header with the
 * global date range and refresh controls, and the routed page content.
 */
export function DashboardLayout({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  // Close the mobile drawer when navigation changes the route
  // (conditional adjustment during render — https://react.dev/reference/react/useState#storing-information-from-previous-renders).
  const [lastPathname, setLastPathname] = useState(pathname);
  if (lastPathname !== pathname) {
    setLastPathname(pathname);
    setMobileOpen(false);
  }

  return (
    <div className="relative flex min-h-screen bg-canvas">
      <div className="ambient" aria-hidden />

      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onToggleCollapse={() => setCollapsed((value) => !value)}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col transition-[padding] duration-200",
          collapsed ? "lg:pl-[72px]" : "lg:pl-[240px]",
        )}
      >
        <Header onOpenMobileNav={() => setMobileOpen(true)} />
        <main className="flex-1 px-4 py-5 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
