import Link from "next/link";

import {
  ArrowUpRight,
  BrandMark,
  ShieldIcon,
} from "@/components/icons";
import { siteConfig } from "@/lib/site";

const platformLinks = [
  { label: "Capabilities", href: "#capabilities" },
  { label: "Architecture", href: "#architecture" },
  { label: "Data standard", href: "#data" },
  { label: "Roadmap", href: "#roadmap" },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-line/70">
      <div className="shell py-12 sm:py-14">
        <div className="flex flex-col gap-12 md:flex-row md:items-start md:justify-between">
          <div className="max-w-sm">
            <Link href="/" className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-[10px] border border-primary/20 bg-primary/5 text-primary">
                <BrandMark className="size-5" />
              </span>
              <span className="text-[15px] font-medium tracking-[-0.02em]">
                EcoPulse <span className="text-muted">AI</span>
              </span>
            </Link>
            <p className="mt-5 text-sm leading-6 text-muted">
              Local-first energy intelligence for monitoring consumption,
              forecasting demand, and explaining anomalies with real data.
            </p>
            <p className="mt-5 inline-flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.14em] text-muted/60">
              <ShieldIcon className="size-3.5 text-primary/70" />
              No cloud dependency
            </p>
          </div>

          <div className="grid grid-cols-2 gap-10 sm:gap-20">
            <div>
              <p className="eyebrow text-muted/60">Platform</p>
              <ul className="mt-4 space-y-3">
                {platformLinks.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      className="text-[13px] text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="eyebrow text-muted/60">API</p>
              <ul className="mt-4 space-y-3">
                <li>
                  <a
                    href={siteConfig.apiDocsUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="group inline-flex items-center gap-1.5 text-[13px] text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  >
                    Swagger UI
                    <ArrowUpRight className="size-3 text-muted/50 transition-colors group-hover:text-primary" />
                  </a>
                </li>
                <li>
                  <a
                    href={siteConfig.apiHealthUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="group inline-flex items-center gap-1.5 text-[13px] text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  >
                    Health JSON
                    <ArrowUpRight className="size-3 text-muted/50 transition-colors group-hover:text-primary" />
                  </a>
                </li>
                <li>
                  <a
                    href={`${siteConfig.apiUrl}/openapi.json`}
                    target="_blank"
                    rel="noreferrer"
                    className="group inline-flex items-center gap-1.5 text-[13px] text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  >
                    OpenAPI schema
                    <ArrowUpRight className="size-3 text-muted/50 transition-colors group-hover:text-primary" />
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-line/60 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted/50">
            © 2026 EcoPulse AI · Solo portfolio project
          </p>
          <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted/50">
            Phase 01 · Foundation · v{siteConfig.version}
          </p>
        </div>
      </div>
    </footer>
  );
}
