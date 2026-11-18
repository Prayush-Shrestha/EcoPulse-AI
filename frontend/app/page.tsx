import { ArchitectureFlow } from "@/components/architecture-flow";
import {
  ActivityIcon,
  AlertIcon,
  ArrowDown,
  ArrowUpRight,
  CheckIcon,
  InfoIcon,
  MinusIcon,
  ShieldIcon,
  TrendIcon,
} from "@/components/icons";
import { SectionLabel } from "@/components/section-label";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { StatusPanel } from "@/components/status-panel";

const capabilities = [
  {
    index: "01",
    title: "Monitoring",
    question: "What is consuming energy?",
    description:
      "Interval-level load data, normalised units, and transparent data-quality flags create a trustworthy baseline before any modelling begins.",
    tools: ["Pandas", "PostgreSQL"],
    icon: ActivityIcon,
  },
  {
    index: "02",
    title: "Forecasting",
    question: "What happens next?",
    description:
      "Seasonal baselines and supervised models, evaluated with chronological splits and documented error metrics rather than optimistic random splits.",
    tools: ["scikit-learn", "Joblib"],
    icon: TrendIcon,
  },
  {
    index: "03",
    title: "Anomaly detection",
    question: "What changed?",
    description:
      "Statistical and unsupervised methods surface deviations in context, with enough evidence to explain why a period warrants attention.",
    tools: ["PySpark", "scikit-learn"],
    icon: AlertIcon,
  },
];

const ledger = [
  { label: "Build scope", value: "Phase 01 · Foundation" },
  { label: "Execution", value: "Local Windows 11" },
  { label: "Data standard", value: "Open datasets only" },
];

const foundationItems = [
  "Next.js app shell and design tokens",
  "FastAPI health endpoints with graceful database checks",
  "SQLAlchemy session layer and Alembic baseline",
  "Docker Compose and GitHub Actions foundations",
];

const excludedItems = [
  "Dataset ingestion or stored energy readings",
  "Trained models, forecasts, or anomaly scores",
  "Dashboard statistics or charts",
  "Authentication, deployment, or cloud services",
];

const datasets = [
  {
    source: "UCI Machine Learning Repository",
    title: "Individual household electric power consumption",
    description:
      "Minute-level residential consumption measurements from a single household, 2006-2010.",
    meta: "Household · Minute-level",
    href: "https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption",
  },
  {
    source: "ENTSO-E Transparency Platform",
    title: "European electricity load and generation",
    description:
      "Hourly load, generation, and cross-border exchange data for European bidding zones.",
    meta: "Grid · Hourly",
    href: "https://transparency.entsoe.eu/",
  },
  {
    source: "U.S. Energy Information Administration",
    title: "EIA Open Data - electricity",
    description:
      "Regional demand, generation, and interchange series available through a free API key.",
    meta: "Regional · Hourly",
    href: "https://www.eia.gov/opendata/",
  },
];

const phases = [
  {
    number: "01",
    title: "Foundation",
    description:
      "Monorepo, product surface, API health contract, PostgreSQL wiring, local containers, and CI.",
    status: "Current",
  },
  {
    number: "02",
    title: "Data foundation",
    description:
      "Dataset acquisition, validation, schema migrations, Airflow orchestration, and Spark processing.",
    status: "Planned",
  },
  {
    number: "03",
    title: "Intelligence",
    description:
      "Time-series features, forecast baselines, anomaly detection, and documented model evaluation.",
    status: "Planned",
  },
  {
    number: "04",
    title: "Experience",
    description:
      "Real-data dashboard views for consumption, forecasts, and anomalies, plus integration tests.",
    status: "Planned",
  },
];

export default function Home() {
  return (
    <>
      <div className="ambient" aria-hidden />
      <SiteHeader />

      <main>
        <section className="relative overflow-hidden border-b border-line/60">
          <div className="shell grid gap-14 py-20 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-center lg:gap-12 lg:py-24 xl:gap-20">
            <div>
              <div className="inline-flex items-center gap-2.5 rounded-full border border-primary/15 bg-primary/5 px-3 py-1.5">
                <span
                  className="size-1.5 rounded-full bg-primary"
                  aria-hidden
                />
                <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-primary">
                  Phase 01 · Foundation
                </span>
              </div>

              <h1 className="mt-7 text-[clamp(2.75rem,5.5vw,5rem)] font-medium leading-[0.96] tracking-[-0.055em]">
                See the signal in
                <span className="block text-primary">every kilowatt.</span>
              </h1>

              <p className="mt-7 max-w-xl text-[15px] leading-7 text-muted sm:text-base sm:leading-7">
                EcoPulse AI is a local-first energy intelligence platform for
                monitoring consumption, forecasting demand, and explaining
                anomalies. It is being built end-to-end on real public datasets
                - with no cloud services and no synthetic production data.
              </p>

              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <a href="#architecture" className="btn-primary">
                  Explore the architecture
                  <ArrowDown className="size-4" />
                </a>
                <a href="#data" className="btn-secondary">
                  Our data standard
                  <ShieldIcon className="size-4 text-primary/80" />
                </a>
              </div>

              <p className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[9px] uppercase tracking-[0.14em] text-muted/60">
                <span className="inline-flex items-center gap-2">
                  <span
                    className="size-1 rounded-full bg-primary/70"
                    aria-hidden
                  />
                  Local by default
                </span>
                <span className="hidden h-3 w-px bg-line sm:block" aria-hidden />
                <span>Real data only</span>
                <span className="hidden h-3 w-px bg-line sm:block" aria-hidden />
                <span>Phase 01 foundation</span>
              </p>
            </div>

            <div className="lg:pl-2">
              <StatusPanel />
            </div>
          </div>

          <div className="border-t border-line/60">
            <dl className="shell grid divide-y divide-line/60 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
              {ledger.map((item) => (
                <div
                  key={item.label}
                  className="py-5 sm:px-6 sm:first:pl-0 sm:last:pr-0"
                >
                  <dt className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted/50">
                    {item.label}
                  </dt>
                  <dd className="mt-1.5 text-[13px] text-ink/90">
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section
          id="capabilities"
          className="scroll-mt-24 border-b border-line/60 py-24 sm:py-28"
        >
          <div className="shell">
            <div className="grid gap-8 lg:grid-cols-[1fr_1fr] lg:items-end lg:gap-20">
              <div>
                <SectionLabel index="01">Capability map</SectionLabel>
                <h2 className="mt-6 text-3xl font-medium tracking-[-0.04em] sm:text-4xl">
                  One system.
                  <span className="block text-muted">Three questions.</span>
                </h2>
              </div>
              <p className="max-w-md text-sm leading-7 text-muted lg:justify-self-end">
                The analytical scope is intentionally narrow. Each module
                answers a specific operational question and passes a documented
                contract to the next layer.
              </p>
            </div>

            <div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-line bg-line md:grid-cols-3">
              {capabilities.map((capability) => {
                const Icon = capability.icon;

                return (
                  <article
                    key={capability.index}
                    className="flex h-full flex-col bg-surface p-6 transition-colors hover:bg-surface-raised/60 sm:p-7"
                  >
                    <div className="flex items-center justify-between">
                      <span className="grid size-9 place-items-center rounded-lg border border-line bg-canvas text-primary">
                        <Icon className="size-4" />
                      </span>
                      <span className="font-mono text-[9px] tracking-[0.14em] text-muted/40">
                        {capability.index}
                      </span>
                    </div>
                    <h3 className="mt-7 text-base font-medium tracking-[-0.015em]">
                      {capability.title}
                    </h3>
                    <p className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-primary/60">
                      {capability.question}
                    </p>
                    <p className="mt-4 flex-1 text-sm leading-6 text-muted">
                      {capability.description}
                    </p>
                    <div className="mt-7 flex flex-wrap gap-1.5 border-t border-line/60 pt-4">
                      {capability.tools.map((tool) => (
                        <span key={tool} className="chip">
                          {tool}
                        </span>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>

            <p className="mt-5 flex max-w-3xl items-start gap-2.5 text-[11px] leading-5 text-muted/60">
              <InfoIcon className="mt-0.5 size-3.5 shrink-0 text-muted/50" />
              This is the capability map for the completed project. Phase 1
              ships the foundation only; no models or consumption metrics are
              implemented yet.
            </p>
          </div>
        </section>

        <section
          id="architecture"
          className="scroll-mt-24 border-b border-line/60 bg-surface/20 py-24 sm:py-28"
        >
          <div className="shell">
            <div className="grid gap-8 lg:grid-cols-[1fr_1fr] lg:items-end lg:gap-20">
              <div>
                <SectionLabel index="02">Architecture</SectionLabel>
                <h2 className="mt-6 text-3xl font-medium tracking-[-0.04em] sm:text-4xl">
                  From source data
                  <span className="block text-muted">to a clear signal.</span>
                </h2>
              </div>
              <p className="max-w-md text-sm leading-7 text-muted lg:justify-self-end">
                Every layer has one responsibility, a typed boundary, and a
                local execution path. The full data pipeline stays inspectable
                from ingestion through to the interface.
              </p>
            </div>

            <div className="mt-12">
              <ArchitectureFlow />
            </div>

            <div className="mt-6 grid gap-6 md:grid-cols-2">
              <div className="rounded-xl border border-line/70 bg-canvas/40 p-6">
                <p className="eyebrow text-muted/70">In this repository</p>
                <ul className="mt-4 space-y-3">
                  {foundationItems.map((item) => (
                    <li
                      key={item}
                      className="flex items-start gap-2.5 text-[13px] leading-5 text-ink/80"
                    >
                      <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-primary/70" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-xl border border-line/70 bg-canvas/40 p-6">
                <p className="eyebrow text-muted/70">Not in Phase 1</p>
                <ul className="mt-4 space-y-3">
                  {excludedItems.map((item) => (
                    <li
                      key={item}
                      className="flex items-start gap-2.5 text-[13px] leading-5 text-muted"
                    >
                      <MinusIcon className="mt-0.5 size-3.5 shrink-0 text-muted/40" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section
          id="data"
          className="scroll-mt-24 border-b border-line/60 py-24 sm:py-28"
        >
          <div className="shell grid gap-14 lg:grid-cols-[0.85fr_1.15fr] lg:gap-20">
            <div className="lg:sticky lg:top-28 lg:self-start">
              <SectionLabel index="03">Data provenance</SectionLabel>
              <h2 className="mt-6 text-3xl font-medium tracking-[-0.04em] sm:text-4xl">
                Real data.
                <span className="block text-muted">No stagecraft.</span>
              </h2>
              <p className="mt-6 max-w-md text-sm leading-7 text-muted">
                Every future metric will be computed from a public dataset that
                is downloaded locally, documented, and reproducible. Dataset
                selection happens in Phase 2; no sample production data is
                shipped in the meantime.
              </p>

              <blockquote className="mt-9 border-l-2 border-primary/40 pl-5">
                <p className="text-sm leading-6 text-ink/90">
                  &ldquo;If a number cannot be reproduced from a documented
                  dataset, it does not belong on screen.&rdquo;
                </p>
                <footer className="mt-3 font-mono text-[9px] uppercase tracking-[0.14em] text-muted/50">
                  Project data rule
                </footer>
              </blockquote>

              <p className="mt-7 font-mono text-[9px] uppercase leading-5 tracking-[0.12em] text-muted/50">
                Raw files remain immutable in data/raw.
                <br />
                Processed outputs are derived, never hand-edited.
              </p>
            </div>

            <div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted">
                  Dataset shortlist
                </p>
                <span className="chip">Selected in Phase 2</span>
              </div>

              <div className="mt-4 space-y-3">
                {datasets.map((dataset) => (
                  <a
                    key={dataset.title}
                    href={dataset.href}
                    target="_blank"
                    rel="noreferrer"
                    className="group block rounded-xl border border-line/80 bg-surface p-5 transition-colors hover:border-primary/25 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 sm:p-6"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted/60">
                        {dataset.source}
                      </p>
                      <ArrowUpRight className="size-4 shrink-0 text-muted/40 transition-colors group-hover:text-primary" />
                    </div>
                    <h3 className="mt-3 text-sm font-medium text-ink">
                      {dataset.title}
                    </h3>
                    <p className="mt-2 text-[13px] leading-6 text-muted">
                      {dataset.description}
                    </p>
                    <p className="mt-4 font-mono text-[9px] uppercase tracking-[0.12em] text-muted/50">
                      {dataset.meta}
                    </p>
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                ))}
              </div>

              <div className="mt-4 rounded-xl border border-dashed border-line p-5">
                <p className="text-xs leading-6 text-muted/70">
                  Raw files are downloaded into{" "}
                  <code className="rounded bg-canvas px-1.5 py-0.5 font-mono text-[10px] text-ink/80">
                    data/raw
                  </code>{" "}
                  and ignored by Git. Phase 2 adds a manifest with source URL,
                  retrieval date, licence, and checksum for every file.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section
          id="roadmap"
          className="scroll-mt-24 py-24 sm:py-28"
        >
          <div className="shell grid gap-14 lg:grid-cols-[0.85fr_1.15fr] lg:gap-20">
            <div>
              <SectionLabel index="04">Roadmap</SectionLabel>
              <h2 className="mt-6 text-3xl font-medium tracking-[-0.04em] sm:text-4xl">
                Built in
                <span className="block text-muted">deliberate phases.</span>
              </h2>
              <p className="mt-6 max-w-md text-sm leading-7 text-muted">
                The repository advances only when the previous layer is
                reproducible. Phase 1 stops at the foundation; later phases are
                documented but deliberately not implemented yet.
              </p>
              <p className="mt-7 inline-flex items-center gap-2.5 rounded-lg border border-line bg-surface px-3.5 py-2.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted/70">
                <span className="size-1.5 rounded-full bg-primary" aria-hidden />
                Current scope · Phase 01
              </p>
            </div>

            <ol>
              {phases.map((phase) => {
                const isCurrent = phase.status === "Current";

                return (
                  <li
                    key={phase.number}
                    className="relative border-l border-line/70 pb-10 pl-6 last:pb-0 sm:pl-8"
                  >
                    <span
                      className={`absolute -left-[5px] top-1.5 size-2.5 rounded-full ${
                        isCurrent
                          ? "bg-primary ring-4 ring-primary/10"
                          : "border border-line bg-canvas"
                      }`}
                      aria-hidden
                    />
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-mono text-[9px] text-muted/50">
                        PHASE {phase.number}
                      </span>
                      <span
                        className={`font-mono text-[9px] uppercase tracking-[0.12em] ${
                          isCurrent ? "text-primary" : "text-muted/40"
                        }`}
                      >
                        {phase.status}
                      </span>
                    </div>
                    <h3 className="mt-2 text-base font-medium tracking-[-0.015em]">
                      {phase.title}
                    </h3>
                    <p className="mt-1.5 max-w-lg text-sm leading-6 text-muted">
                      {phase.description}
                    </p>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
