import Link from "next/link";

import { ArrowUpRight, BrandMark } from "@/components/icons";
import { siteConfig } from "@/lib/site";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-line/70 bg-canvas/80 backdrop-blur-xl">
      <div className="shell flex h-[72px] items-center justify-between gap-6">
        <Link
          href="/"
          className="group flex items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-4 focus-visible:ring-offset-canvas"
        >
          <span className="grid size-9 place-items-center rounded-[10px] border border-primary/20 bg-primary/5 text-primary transition-colors group-hover:border-primary/40">
            <BrandMark className="size-5" />
          </span>
          <span className="text-[15px] font-medium tracking-[-0.02em]">
            EcoPulse <span className="text-muted">AI</span>
          </span>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-7 lg:flex">
          {siteConfig.nav.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="rounded-sm text-[13px] text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-4 focus-visible:ring-offset-canvas"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-4">
          <span className="hidden font-mono text-[9px] uppercase tracking-[0.16em] text-muted/60 md:inline">
            Phase 01
          </span>
          <span className="hidden h-4 w-px bg-line md:block" aria-hidden />
          <a
            href={siteConfig.apiDocsUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md text-[12px] font-medium text-ink transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-4 focus-visible:ring-offset-canvas"
          >
            API reference
            <ArrowUpRight className="size-3.5 text-muted" />
          </a>
        </div>
      </div>
    </header>
  );
}
