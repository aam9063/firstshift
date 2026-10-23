import { useQuery } from "@tanstack/react-query";
import { fetchOverview } from "../../api/client";
import type { ActivityItem, AttentionItem, CoverageRow, FunnelSummary } from "../../api/types";
import { KpiTile } from "./KpiTile";

const ATTENTION_LABELS: Record<AttentionItem["kind"], string> = {
  sla_breach: "SLA BREACH",
  first_shift: "FIRST SHIFT",
  human_needed: "HUMAN NEEDED",
  dlq: "DLQ",
  eval: "EVAL",
};

function ActorDot({ type }: { type: ActivityItem["actorType"] }) {
  const color =
    type === "agent"
      ? "bg-brand-tag"
      : type === "human"
        ? "bg-testimonial-orange"
        : "bg-steel";
  return <span aria-hidden className={`inline-block h-1.5 w-1.5 rounded-full ${color}`} />;
}

function NeedsAttentionItem({ item }: { item: AttentionItem }) {
  const urgent = item.kind === "sla_breach" || item.kind === "dlq";
  return (
    <li className="flex flex-col gap-1 border-b border-hairline-soft py-3 last:border-b-0">
      <div className="flex items-center justify-between">
        <span
          className={`rounded-sm px-1.5 py-0.5 text-micro font-semibold ${
            urgent ? "bg-brand-error/10 text-brand-error" : "bg-surface text-charcoal"
          }`}
        >
          {ATTENTION_LABELS[item.kind]}
        </span>
        <span className="text-micro text-stone">{item.ago}</span>
      </div>
      <p className="text-body-sm-medium text-ink">{item.title}</p>
      <p className="text-micro text-steel">{item.detail}</p>
    </li>
  );
}

function Funnel({ funnel }: { funnel: FunnelSummary }) {
  return (
    <ul className="flex flex-col gap-2">
      {funnel.stages.map((stage) => (
        <li key={stage.id} className="flex items-center gap-3">
          <span className="w-36 shrink-0 text-body-sm text-charcoal">{stage.label}</span>
          <div className="flex flex-1 flex-col gap-1">
            <div className="h-2 rounded-full bg-ink" style={{ width: `${stage.pilotPct}%` }} />
            <div className="h-2 rounded-full bg-muted" style={{ width: `${stage.controlPct}%` }} />
          </div>
          <span className="w-24 shrink-0 text-right text-micro text-steel">
            {stage.pilotPct}% / {stage.controlPct}%
          </span>
        </li>
      ))}
    </ul>
  );
}

function CoverageTable({ rows }: { rows: CoverageRow[] }) {
  return (
    <div className="overflow-x-auto">
    <table className="w-full min-w-[480px] text-left">
      <thead>
        <tr className="text-micro uppercase tracking-wide text-steel">
          <th className="py-2 font-semibold">Restaurant</th>
          <th className="py-2 font-semibold">Open</th>
          <th className="py-2 font-semibold">Covered</th>
          <th className="py-2 font-semibold">Bench</th>
          <th className="py-2 font-semibold">Manager reply</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className="border-t border-hairline-soft text-body-sm">
            <td className="py-2.5">
              <span className="text-ink">{row.restaurant}</span>
              <span
                className={`ml-2 rounded-sm px-1.5 py-0.5 text-micro font-semibold ${
                  row.cohort === "pilot" ? "bg-canvas-dark text-on-dark" : "bg-surface text-steel"
                }`}
              >
                {row.cohort === "pilot" ? "Pilot" : "Control"}
              </span>
            </td>
            <td className="py-2.5 text-charcoal">{row.openShifts}</td>
            <td className="py-2.5">
              <span className="mr-2 text-charcoal">{row.coveredPct}%</span>
              <span className="inline-block h-1.5 w-16 rounded-full bg-surface align-middle">
                <span
                  className={`block h-1.5 rounded-full ${
                    row.coveredPct >= 80 ? "bg-brand-green" : "bg-testimonial-orange"
                  }`}
                  style={{ width: `${row.coveredPct}%` }}
                />
              </span>
            </td>
            <td className="py-2.5 text-charcoal">{row.bench}</td>
            <td className="py-2.5 text-charcoal">{row.managerReply}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

export function OverviewPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["overview"],
    queryFn: fetchOverview,
  });

  if (isLoading || !data) {
    return <p className="text-body-sm text-steel">Loading overview...</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-micro font-semibold uppercase tracking-wide text-steel">
          Pilot - Costa Blanca
        </p>
        <h1 className="text-heading-3 font-semibold text-ink">Overview</h1>
        <p className="mt-1 text-body-sm text-steel">
          12 pilot and 3 control restaurants - last 18 days - compared with the 12-month baseline
        </p>
      </div>

      <section aria-label="KPI cards" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {data.kpis.map((kpi) => (
          <KpiTile key={kpi.id} kpi={kpi} />
        ))}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <section aria-label="Hiring funnel" className="rounded-lg border border-hairline-soft bg-canvas p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-heading-5 font-semibold text-ink">Hiring funnel</h2>
            <p className="text-micro text-steel">
              Pilot - {data.funnel.pilotCandidates} - Control - {data.funnel.controlCandidates}
            </p>
          </div>
          <p className="mt-1 text-micro text-steel">Share of applicants reaching each stage</p>
          <div className="mt-4">
            <Funnel funnel={data.funnel} />
          </div>
          <p className="mt-4 rounded-md bg-brand-green-soft px-3 py-2 text-body-sm text-charcoal">
            {data.funnel.insight}
          </p>
        </section>

        <section aria-label="Needs attention" className="rounded-lg border border-hairline-soft bg-canvas p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-heading-5 font-semibold text-ink">Needs attention</h2>
            <button type="button" className="text-body-sm-medium text-ink underline-offset-2">
              View all
            </button>
          </div>
          <ul className="mt-2">
            {data.attention.map((item) => (
              <NeedsAttentionItem key={item.id} item={item} />
            ))}
          </ul>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <section aria-label="Recent activity" className="rounded-lg border border-hairline-soft bg-canvas p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-heading-5 font-semibold text-ink">Recent activity</h2>
            <button type="button" className="text-body-sm-medium text-ink underline-offset-2">
              Open live feed
            </button>
          </div>
          <ul className="mt-2">
            {data.activity.map((item) => (
              <li
                key={item.id}
                className="flex items-start gap-3 border-b border-hairline-soft py-2.5 last:border-b-0"
              >
                <span className="w-14 shrink-0 pt-0.5 font-mono text-micro text-stone">{item.at}</span>
                <span className="flex w-28 shrink-0 items-center gap-1.5 pt-0.5 text-body-sm text-charcoal">
                  <ActorDot type={item.actorType} />
                  {item.actorLabel}
                </span>
                <span className="min-w-0">
                  <span className="text-body-sm text-ink">{item.summary}</span>
                  <span className="ml-2 font-mono text-micro text-stone">{item.eventType}</span>
                  {item.detailTag && (
                    <span className="ml-2 font-mono text-micro text-stone">{item.detailTag}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="Shift coverage" className="rounded-lg border border-hairline-soft bg-canvas p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-heading-5 font-semibold text-ink">Shift coverage, next 14 days</h2>
            <span className="text-micro text-steel">All restaurants</span>
          </div>
          <div className="mt-2">
            <CoverageTable rows={data.coverage} />
          </div>
        </section>
      </div>
    </div>
  );
}
