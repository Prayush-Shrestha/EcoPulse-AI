const stages = [
  {
    code: "01",
    label: "Ingest",
    title: "Sources",
    description: "Open energy datasets enter through a documented acquisition step.",
    tools: ["UCI", "ENTSO-E", "EIA"],
  },
  {
    code: "02",
    label: "Orchestrate",
    title: "Airflow",
    description: "Scheduled, observable runs keep ingestion and processing repeatable.",
    tools: ["Apache Airflow"],
  },
  {
    code: "03",
    label: "Transform",
    title: "Pandas / PySpark",
    description: "Validation, unit normalisation, and time-series feature preparation.",
    tools: ["Pandas", "PySpark"],
  },
  {
    code: "04",
    label: "Store",
    title: "PostgreSQL",
    description: "A versioned relational schema owns processed readings and model inputs.",
    tools: ["PostgreSQL 17", "Alembic"],
  },
  {
    code: "05",
    label: "Learn",
    title: "scikit-learn",
    description: "Forecast baselines and anomaly detection with chronological evaluation.",
    tools: ["scikit-learn", "Joblib"],
  },
  {
    code: "06",
    label: "Serve",
    title: "API / UI",
    description: "A typed local API feeds a focused analytics interface.",
    tools: ["FastAPI", "Next.js", "Recharts"],
  },
];

export function ArchitectureFlow() {
  return (
    <div className="rounded-2xl border border-line bg-canvas/70 p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 pb-5">
        <div className="flex items-center gap-2.5">
          <span className="size-1.5 rounded-full bg-primary" aria-hidden />
          <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted">
            Target data path
          </span>
        </div>
        <span className="chip">Local only</span>
      </div>

      <ol className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {stages.map((stage) => (
          <li
            key={stage.code}
            className="flex flex-col rounded-xl border border-line/80 bg-surface/50 p-5 transition-colors hover:border-primary/20 hover:bg-surface/80"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-primary/70">
                {stage.code}
              </span>
              <span className="font-mono text-[8px] uppercase tracking-[0.14em] text-muted/50">
                {stage.label}
              </span>
            </div>
            <h3 className="mt-4 text-sm font-medium tracking-[-0.01em]">
              {stage.title}
            </h3>
            <p className="mt-2 flex-1 text-xs leading-5 text-muted">
              {stage.description}
            </p>
            <div className="mt-5 flex flex-wrap gap-1.5 border-t border-line/60 pt-3">
              {stage.tools.map((tool) => (
                <span
                  key={tool}
                  className="font-mono text-[9px] uppercase tracking-[0.06em] text-muted/70"
                >
                  {tool}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ol>

      <p className="mt-6 border-t border-line/60 pt-4 text-[11px] leading-5 text-muted/60">
        Airflow and Spark will run in Docker. The API and web application remain
        usable without the data pipeline while the foundation is being built.
      </p>
    </div>
  );
}
