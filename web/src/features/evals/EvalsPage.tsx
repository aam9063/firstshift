import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, fetchEvalReport, fetchEvalVersions } from "../../api/client";
import type { EvalConversation, EvalReport, EvalSummaryRow } from "../../api/types";

/* Evals (specs/04b-console.md section 3.7, odd/tasks/console-views.md T3/S3):
   the version list, a comparison of any two versions (metric deltas,
   deterministic checks, judge scores by criterion, fairness with ratios under
   0.8 highlighted, cost per hire) and a read-only replay of the worst
   conversations from the report transcripts. */

const FAIRNESS_THRESHOLD = 0.8;

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${Math.round(value * 100)}%`;
}

function num(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? "n/a" : value.toFixed(digits);
}

function Delta({ base, compare }: { base: number; compare: number }) {
  const delta = compare - base;
  const sign = delta > 0 ? "+" : "";
  return (
    <span className="font-mono text-micro text-charcoal">
      {sign}
      {Number.isInteger(delta * 100) && Math.abs(delta) < 1 ? `${sign}${Math.round(delta * 100)} pts` : delta.toFixed(2)}
    </span>
  );
}

interface MetricRow {
  label: string;
  key: keyof EvalReport["summary"];
  source: string;
  format: (value: number) => string;
}

const METRICS: MetricRow[] = [
  { label: "Task success rate", key: "task_success_rate", source: "summary.task_success_rate = successful conversations / total", format: pct },
  { label: "Interview show rate", key: "interview_show_rate", source: "summary.interview_show_rate = attended / booked", format: pct },
  { label: "Day-1 show rate", key: "day1_show_rate", source: "summary.day1_show_rate = worked / scheduled first shifts", format: pct },
  { label: "Median TTFPS (h)", key: "median_ttfps_hours", source: "summary.median_ttfps_hours", format: (value) => value.toFixed(1) },
  { label: "Mean judge score", key: "mean_judge_score", source: "summary.mean_judge_score = mean judge mean across conversations", format: (value) => value.toFixed(3) },
  { label: "Deterministic failures", key: "deterministic_failures", source: "summary.deterministic_failures", format: (value) => String(value) },
  { label: "Cost per hire (USD)", key: "cost_per_hired_usd", source: "summary.cost_per_hired_usd = total_cost_usd / hired", format: (value) => value.toFixed(6) },
];

function Comparison({ base, compare }: { base: EvalReport; compare: EvalReport }) {
  return (
    <div className="overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="border-b border-hairline-soft text-micro font-semibold uppercase tracking-wide text-steel">
              <th scope="col" className="px-4 py-2 font-semibold">Metric</th>
              <th scope="col" className="px-4 py-2 font-semibold">{base.meta.label}</th>
              <th scope="col" className="px-4 py-2 font-semibold">{compare.meta.label}</th>
              <th scope="col" className="px-4 py-2 font-semibold">Delta</th>
            </tr>
          </thead>
          <tbody>
            {METRICS.map((metric) => {
              const baseValue = base.summary[metric.key];
              const compareValue = compare.summary[metric.key];
              return (
                <tr key={metric.label} className="border-b border-hairline-soft last:border-b-0">
                  <td className="px-4 py-2 text-body-sm text-ink" title={`GET /api/evals/{version} - ${metric.source}`}>
                    {metric.label}
                  </td>
                  <td className="px-4 py-2 font-mono text-body-sm text-charcoal">{metric.format(baseValue)}</td>
                  <td className="px-4 py-2 font-mono text-body-sm text-charcoal">{metric.format(compareValue)}</td>
                  <td className="px-4 py-2">
                    <Delta base={baseValue} compare={compareValue} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DeterministicChecks({ base, compare }: { base: EvalReport; compare: EvalReport }) {
  const checkNames = [
    ...new Set([
      ...Object.keys(base.deterministic_checks.per_check),
      ...Object.keys(compare.deterministic_checks.per_check),
    ]),
  ];
  return (
    <div className="overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
      <table className="w-full min-w-[560px] text-left">
        <thead>
          <tr className="border-b border-hairline-soft text-micro font-semibold uppercase tracking-wide text-steel">
            <th scope="col" className="px-4 py-2 font-semibold">Check</th>
            <th scope="col" className="px-4 py-2 font-semibold">{base.meta.label}</th>
            <th scope="col" className="px-4 py-2 font-semibold">{compare.meta.label}</th>
          </tr>
        </thead>
        <tbody>
          {checkNames.map((name) => {
            const baseStat = base.deterministic_checks.per_check[name];
            const compareStat = compare.deterministic_checks.per_check[name];
            return (
              <tr key={name} className="border-b border-hairline-soft last:border-b-0">
                <td className="px-4 py-2 font-mono text-caption text-ink">{name}</td>
                <td className="px-4 py-2 font-mono text-caption text-charcoal">
                  {baseStat ? `${baseStat.passed} passed / ${baseStat.failed} failed` : "not reported"}
                </td>
                <td className="px-4 py-2 font-mono text-caption text-charcoal">
                  {compareStat ? `${compareStat.passed} passed / ${compareStat.failed} failed` : "not reported"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function reportConversations(report: EvalReport): EvalConversation[] {
  /* The console reads judge scores from every conversation the report ships,
     including the worst_5 replay set. */
  const seen = new Set<string>();
  const merged: EvalConversation[] = [];
  for (const conversation of [...report.conversations, ...report.worst_5]) {
    if (seen.has(conversation.conversation_id)) continue;
    seen.add(conversation.conversation_id);
    merged.push(conversation);
  }
  return merged;
}

function judgeCriteria(base: EvalReport, compare: EvalReport): string[] {
  return [...new Set([...reportConversations(base), ...reportConversations(compare)].flatMap(
    (conversation) => Object.keys(conversation.judge_scores ?? {}),
  ))];
}

function meanJudgeScore(report: EvalReport, criterion: string): number | null {
  const withScore = reportConversations(report).filter(
    (conversation) => typeof conversation.judge_scores?.[criterion] === "number",
  );
  if (withScore.length === 0) return null;
  const total = withScore.reduce((sum, conversation) => sum + conversation.judge_scores[criterion], 0);
  return total / withScore.length;
}

function JudgeScores({ base, compare }: { base: EvalReport; compare: EvalReport }) {
  const criteria = judgeCriteria(base, compare);
  if (criteria.length === 0) {
    return (
      <p className="rounded-lg border border-hairline-soft bg-canvas p-6 text-center text-body-sm text-steel">
        The reports expose no per-criterion judge scores yet.
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
      <table className="w-full min-w-[480px] text-left">
        <thead>
          <tr className="border-b border-hairline-soft text-micro font-semibold uppercase tracking-wide text-steel">
            <th scope="col" className="px-4 py-2 font-semibold">Criterion</th>
            <th scope="col" className="px-4 py-2 font-semibold">{base.meta.label}</th>
            <th scope="col" className="px-4 py-2 font-semibold">{compare.meta.label}</th>
          </tr>
        </thead>
        <tbody>
          {criteria.map((criterion) => (
            <tr key={criterion} className="border-b border-hairline-soft last:border-b-0">
              <td className="px-4 py-2 font-mono text-caption text-ink">{criterion}</td>
              <td className="px-4 py-2 font-mono text-caption text-charcoal">
                {num(meanJudgeScore(base, criterion))}
              </td>
              <td className="px-4 py-2 font-mono text-caption text-charcoal">
                {num(meanJudgeScore(compare, criterion))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FairnessTable({ base }: { base: EvalReport }) {
  if (base.fairness.length === 0) {
    return (
      <p className="rounded-lg border border-hairline-soft bg-canvas p-6 text-center text-body-sm text-steel">
        The report exposes no fairness table yet.
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
      <table className="w-full min-w-[560px] text-left">
        <thead>
          <tr className="border-b border-hairline-soft text-micro font-semibold uppercase tracking-wide text-steel">
            <th scope="col" className="px-4 py-2 font-semibold">Dimension</th>
            <th scope="col" className="px-4 py-2 font-semibold">Group</th>
            <th scope="col" className="px-4 py-2 font-semibold">Selected</th>
            <th scope="col" className="px-4 py-2 font-semibold">Ratio</th>
          </tr>
        </thead>
        <tbody>
          {base.fairness.map((row) => {
            const underThreshold = row.ratio < FAIRNESS_THRESHOLD;
            return (
              <tr key={`${row.dimension}-${row.group}`} className="border-b border-hairline-soft last:border-b-0">
                <td className="px-4 py-2 font-mono text-caption text-ink">{row.dimension}</td>
                <td className="px-4 py-2 text-body-sm text-charcoal">{row.group}</td>
                <td className="px-4 py-2 font-mono text-caption text-charcoal" title="fairness.selected / fairness.n">
                  {row.selected} / {row.n}
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-caption text-charcoal">{row.ratio.toFixed(2)}</span>
                  {underThreshold && (
                    <span
                      className="ml-2 rounded-sm bg-brand-warn/15 px-1.5 py-0.5 text-micro font-semibold text-charcoal"
                      title={`fairness ratio ${row.ratio} is under ${FAIRNESS_THRESHOLD}: review before shipping this prompt version`}
                    >
                      Under {FAIRNESS_THRESHOLD}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ConversationReplay({ conversation }: { conversation: EvalConversation }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-b border-hairline-soft py-2.5 last:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-body-sm text-ink">
            {conversation.persona_id} · {conversation.label}
          </p>
          <p className="font-mono text-micro text-stone">
            {conversation.scenario} · judge mean {conversation.judge_mean} · ended {conversation.final_state}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink"
        >
          {open ? "Hide conversation" : "Replay conversation"}
        </button>
      </div>
      {open && (
        <div className="mt-2 space-y-2 rounded-lg bg-surface p-3">
          {conversation.transcript.map((line, index) => (
            <p key={index} className="text-caption text-charcoal">
              <span className="font-mono text-micro text-steel">{line.role}: </span>
              {line.text}
            </p>
          ))}
        </div>
      )}
    </li>
  );
}

function VersionSelect({
  label,
  versions,
  value,
  onChange,
}: {
  label: string;
  versions: EvalSummaryRow[];
  value: string;
  onChange: (version: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-body-sm text-steel">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 rounded-md border border-hairline bg-canvas px-2 text-body-sm text-ink"
      >
        {versions.map((version) => (
          <option key={version.version} value={version.version}>
            {version.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function EvalsPage() {
  const versionsQuery = useQuery({ queryKey: ["evals"], queryFn: fetchEvalVersions });
  const versions = versionsQuery.data ?? [];

  const [baseVersion, setBaseVersion] = useState<string>("");
  const [compareVersion, setCompareVersion] = useState<string>("");

  const effectiveBase = baseVersion || versions[0]?.version || "";
  const effectiveCompare = compareVersion || versions[1]?.version || "";

  const baseQuery = useQuery({
    queryKey: ["evals", effectiveBase],
    queryFn: () => fetchEvalReport(effectiveBase),
    enabled: effectiveBase !== "",
  });
  const compareQuery = useQuery({
    queryKey: ["evals", effectiveCompare],
    queryFn: () => fetchEvalReport(effectiveCompare),
    enabled: effectiveCompare !== "" && effectiveCompare !== effectiveBase,
  });

  const base = baseQuery.data;
  const compare = compareQuery.data;

  return (
    <div className="min-w-0">
      <p className="text-micro font-semibold uppercase tracking-wide text-steel">Quality</p>
      <h1 className="text-heading-3 font-semibold text-ink">Evals</h1>
      <p className="mt-1 text-body-sm text-steel">
        Compare any two prompt versions on the same personas and scenarios.
      </p>

      {versionsQuery.isPending && (
        <p role="status" className="mt-6 text-body-sm text-steel">Loading eval versions</p>
      )}
      {versionsQuery.isError && (
        <div role="alert" className="mt-6 rounded-lg border border-hairline bg-canvas p-6">
          <p className="text-body-sm-medium text-brand-error">Could not load eval versions</p>
          <p className="mt-1 text-body-sm text-steel">
            {versionsQuery.error instanceof ApiError ? versionsQuery.error.message : "Unknown error"}
          </p>
        </div>
      )}

      {versions.length > 0 && (
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <VersionSelect
            label="Base version"
            versions={versions}
            value={effectiveBase}
            onChange={setBaseVersion}
          />
          <VersionSelect
            label="Compare version"
            versions={versions}
            value={effectiveCompare}
            onChange={setCompareVersion}
          />
        </div>
      )}

      {versions.length > 0 && (
        <div className="mt-6 overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left">
              <thead>
                <tr className="border-b border-hairline-soft text-micro font-semibold uppercase tracking-wide text-steel">
                  <th scope="col" className="px-4 py-2 font-semibold">Version</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Generated</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Task success</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Cost per hire</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((version: EvalSummaryRow) => (
                  <tr key={version.version} className="border-b border-hairline-soft last:border-b-0 hover:bg-surface">
                    <td className="px-4 py-2 font-mono text-body-sm text-ink">{version.label}</td>
                    <td className="px-4 py-2 font-mono text-caption text-steel">{version.generatedAt}</td>
                    <td
                      className="px-4 py-2 font-mono text-body-sm text-charcoal"
                      title="GET /api/evals - taskSuccessRate = successful conversations / total"
                    >
                      {pct(version.taskSuccessRate)}
                    </td>
                    <td
                      className="px-4 py-2 font-mono text-body-sm text-charcoal"
                      title="GET /api/evals - costPerHireUsd = total cost / hires for this version"
                    >
                      {num(version.costPerHireUsd, 6)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {base && compare && (
        <div className="mt-8 space-y-8">
          <section>
            <h2 className="text-heading-5 font-semibold text-ink">
              Metrics: {base.meta.label} vs {compare.meta.label}
            </h2>
            <div className="mt-3">
              <Comparison base={base} compare={compare} />
            </div>
          </section>

          <section>
            <h2
              className="text-heading-5 font-semibold text-ink"
              title="GET /api/evals/{version} - deterministic_checks.per_check"
            >
              Deterministic checks
            </h2>
            <div className="mt-3">
              <DeterministicChecks base={base} compare={compare} />
            </div>
          </section>

          <section>
            <h2
              className="text-heading-5 font-semibold text-ink"
              title="GET /api/evals/{version} - mean judge score per criterion across conversations"
            >
              Judge scores by criterion
            </h2>
            <div className="mt-3">
              <JudgeScores base={base} compare={compare} />
            </div>
          </section>

          <section>
            <h2
              className="text-heading-5 font-semibold text-ink"
              title="GET /api/evals/{version} - fairness table; selection ratio per group, ratios under 0.8 are flagged"
            >
              Fairness
            </h2>
            <div className="mt-3">
              <FairnessTable base={base} />
            </div>
          </section>

          <section>
            <h2
              className="text-heading-5 font-semibold text-ink"
              title={`GET /api/evals/${base.meta.label} - worst_5 conversations by judge mean; read-only transcript`}
            >
              Worst conversations ({base.meta.label})
            </h2>
            <ul className="mt-3 rounded-lg border border-hairline-soft bg-canvas px-4">
              {base.worst_5.map((conversation) => (
                <ConversationReplay key={conversation.conversation_id} conversation={conversation} />
              ))}
            </ul>
          </section>
        </div>
      )}

      {(baseQuery.isError || compareQuery.isError) && (
        <p role="alert" className="mt-6 text-body-sm text-brand-error">
          Could not load an eval report:{" "}
          {(baseQuery.error ?? compareQuery.error) instanceof ApiError
            ? String((baseQuery.error ?? compareQuery.error)?.message)
            : "unknown error"}
        </p>
      )}
    </div>
  );
}
