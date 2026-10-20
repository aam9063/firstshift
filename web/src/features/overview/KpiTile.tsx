import type { KpiCard } from "../../api/types";

/* Sparklines are inline SVG polylines instead of Recharts: six tiny charts per
   page do not justify the chart runtime. The funnel, the page's real chart,
   uses Recharts (deviation recorded in odd/tasks/console-ui.md). */
function Sparkline({ points }: { points: number[] }) {
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = 100 / (points.length - 1);
  const path = points
    .map((value, index) => {
      const x = index * step;
      const y = 24 - ((value - min) / range) * 20 - 2;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      aria-hidden
      viewBox="0 0 100 24"
      preserveAspectRatio="none"
      className="h-6 w-full text-ink"
    >
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function StatusChip({ status }: { status: KpiCard["status"] }) {
  if (status === "on_target") {
    return (
      <span className="rounded-full bg-brand-green-soft px-2 py-0.5 text-micro font-semibold text-ink">
        On target
      </span>
    );
  }
  return (
    <span className="rounded-full bg-brand-warn/15 px-2 py-0.5 text-micro font-semibold text-ink">
      Below target
    </span>
  );
}

export function KpiTile({ kpi }: { kpi: KpiCard }) {
  return (
    <div className="rounded-lg border border-hairline-soft bg-canvas p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-body-sm-medium text-ink">{kpi.label}</p>
        <StatusChip status={kpi.status} />
      </div>
      <p className="mt-2 text-heading-3 font-semibold text-ink">
        {kpi.value}
        <span className="ml-1 text-body-sm font-normal text-steel">{kpi.unit}</span>
      </p>
      <div className="mt-1">
        <Sparkline points={kpi.trend} />
      </div>
      <dl className="mt-2 space-y-0.5 text-micro text-steel">
        <div className="flex justify-between">
          <dt>Control</dt>
          <dd className="text-charcoal">{kpi.control}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Baseline</dt>
          <dd className="text-charcoal">{kpi.baseline}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Target</dt>
          <dd className="text-charcoal">{kpi.target}</dd>
        </div>
      </dl>
      <p className="mt-2 border-t border-hairline-soft pt-2 font-mono text-micro text-stone">
        GET {kpi.source}
      </p>
    </div>
  );
}
