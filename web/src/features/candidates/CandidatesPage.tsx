import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, fetchCandidates } from "../../api/client";
import type { CandidateListItem, SlaRisk } from "../../api/types";
import { formatDateTime } from "../../lib/dates";

/* Candidates list (specs/04b-console.md section 3.3, odd/tasks/console-live.md
   T3): real rows from GET /api/candidates. Each row links to the candidate
   journey; the table scrolls horizontally inside its card on narrow screens
   and never overflows the page. */

const SLA_RISK: Record<SlaRisk, { label: string; className: string }> = {
  ok: { label: "On track", className: "bg-brand-green-soft text-ink" },
  at_risk: { label: "At risk", className: "bg-brand-warn/10 text-charcoal" },
  breached: { label: "Breached", className: "bg-brand-error/10 text-brand-error" },
};

function SlaRiskChip({ risk }: { risk: SlaRisk }) {
  const chip = SLA_RISK[risk] ?? SLA_RISK.ok;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-micro font-semibold ${chip.className}`}
    >
      <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
      {chip.label}
    </span>
  );
}

function StateChip({ label }: { label: string }) {
  return (
    <span className="inline-block rounded-sm border border-hairline-soft bg-surface px-1.5 py-0.5 text-micro font-medium text-charcoal">
      {label}
    </span>
  );
}


function CandidatesTable({ items }: { items: CandidateListItem[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left">
          <thead>
            <tr className="border-b border-hairline-soft text-micro font-semibold uppercase tracking-wide text-steel">
              <th scope="col" className="px-4 py-2 font-semibold">Candidate</th>
              <th scope="col" className="px-4 py-2 font-semibold">State</th>
              <th scope="col" className="px-4 py-2 font-semibold">Restaurant</th>
              <th scope="col" className="px-4 py-2 font-semibold">Cohort</th>
              <th scope="col" className="px-4 py-2 font-semibold">Language</th>
              <th scope="col" className="px-4 py-2 font-semibold">Last activity</th>
              <th scope="col" className="px-4 py-2 font-semibold">SLA risk</th>
            </tr>
          </thead>
          <tbody>
            {items.map((candidate) => (
              <tr
                key={candidate.id}
                className="border-b border-hairline-soft last:border-b-0 hover:bg-surface"
              >
                <td className="px-4 py-2.5">
                  <Link
                    to={`/candidates/${candidate.id}`}
                    className="text-body-sm-medium text-ink underline-offset-2 hover:underline"
                  >
                    {candidate.firstName}
                    {candidate.initials ? ` (${candidate.initials})` : ""}
                  </Link>
                  <p className="font-mono text-micro text-stone">{candidate.phoneMasked}</p>
                </td>
                <td className="px-4 py-2.5">
                  <StateChip label={candidate.stateLabel} />
                </td>
                <td className="px-4 py-2.5 text-body-sm text-charcoal">{candidate.restaurant}</td>
                <td className="px-4 py-2.5">
                  <span className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-micro text-steel">
                    {candidate.cohort}
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-micro text-steel">
                  {candidate.languages.join(", ")}
                </td>
                <td className="px-4 py-2.5 text-body-sm text-charcoal">
                  {formatDateTime(candidate.lastActivityAt)}
                  {candidate.elapsedLabel ? (
                    <p className="font-mono text-micro text-stone">{candidate.elapsedLabel}</p>
                  ) : null}
                </td>
                <td className="px-4 py-2.5">
                  <SlaRiskChip risk={candidate.slaRisk} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CandidatesPage() {
  const { data, isError, error, refetch, isPending } = useQuery({
    queryKey: ["candidates"],
    queryFn: fetchCandidates,
  });

  return (
    <div className="min-w-0">
      <p className="text-micro font-semibold uppercase tracking-wide text-steel">
        Workspace
      </p>
      <h1 className="text-heading-3 font-semibold text-ink">Candidates</h1>
      <p className="mt-1 text-body-sm text-steel">
        {data ? `${data.total} candidates in the pilot funnel` : "Loading candidates"}
      </p>

      {isPending && (
        <p role="status" className="mt-6 text-body-sm text-steel">
          Loading candidates
        </p>
      )}

      {isError && (
        <div
          role="alert"
          className="mt-6 rounded-lg border border-hairline bg-canvas p-6"
        >
          <p className="text-body-sm-medium text-brand-error">
            Could not load candidates
          </p>
          <p className="mt-1 text-body-sm text-steel">
            {error instanceof ApiError ? error.message : "Unknown error"}
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-4 flex h-11 items-center rounded-full border border-hairline px-4 text-body-sm-medium text-ink"
          >
            Retry
          </button>
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="mt-6 rounded-lg border border-hairline-soft bg-canvas p-8 text-center">
          <p className="text-body-sm-medium text-ink">No candidates yet</p>
          <p className="mt-1 text-body-sm text-steel">
            New applications appear here the moment HireDesk receives them.
          </p>
        </div>
      )}

      {data && data.items.length > 0 && <CandidatesTable items={data.items} />}
    </div>
  );
}
