import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, createErasureRequest, fetchAudit } from "../../api/client";
import type { AuditRow, ErasureResponse } from "../../api/types";
import { formatDateTime } from "../../lib/dates";

/* Compliance (specs/04b-console.md section 3.8, odd/tasks/console-views.md
   T4/S4): audit log search, consent records grouped by notice version,
   erasure requests and their status. This is the DPO view: every action is
   sent with X-Actor-Role: dpo and the role is stated in a notice.

   Backend gaps rendered honestly:
   - consent records are derived from consent audit events (no dedicated
     endpoint); when none are recorded the section shows an empty state.
   - erasure requests have no list endpoint, only POST /api/erasure-requests.
   - retention countdowns have no endpoint. */

function noticeVersionsFromPayload(payload: Record<string, unknown>): string[] {
  /* Consent audit events fold the consent.recorded event into their payload;
     the notice version lives there (see app/api/webhooks.py NOTICE_VERSION). */
  const folded = payload.folded_events;
  if (!Array.isArray(folded)) return [];
  const versions: string[] = [];
  for (const entry of folded) {
    const inner = (entry as { payload?: Record<string, unknown> }).payload;
    const version = inner?.notice_version;
    if (typeof version === "string") versions.push(version);
  }
  return versions;
}

function AuditSearch() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState<{ q?: string }>({});
  const { data, isError, error, isPending, isFetching } = useQuery({
    queryKey: ["audit", submitted],
    queryFn: () => fetchAudit(submitted),
  });

  return (
    <div>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(query.trim() ? { q: query.trim() } : {});
        }}
      >
        <div className="flex-1">
          <label htmlFor="audit-search" className="sr-only">
            Search audit log
          </label>
          <input
            id="audit-search"
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Event type, actor, state, payload text"
            className="h-10 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink outline-none focus:border-brand-green"
          />
        </div>
        <button
          type="submit"
          className="flex h-10 items-center justify-center rounded-full bg-primary px-4 text-body-sm-medium text-on-primary"
        >
          Search
        </button>
      </form>

      <p className="mt-2 font-mono text-micro text-stone" title="GET /api/audit with q, eventType, candidateId, limit, offset">
        GET /api/audit
      </p>

      {isPending && (
        <p role="status" className="mt-4 text-body-sm text-steel">Loading audit log</p>
      )}
      {isError && (
        <p role="alert" className="mt-4 text-body-sm text-brand-error">
          Could not load the audit log: {error instanceof ApiError ? error.message : "unknown error"}
        </p>
      )}
      {data && (
        <div className="mt-3 overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left">
              <thead>
                <tr className="border-b border-hairline-soft text-micro font-semibold uppercase tracking-wide text-steel">
                  <th scope="col" className="px-4 py-2 font-semibold">When (UTC)</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Actor</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Event</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Transition</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row: AuditRow) => (
                  <tr key={row.id} className="border-b border-hairline-soft last:border-b-0">
                    <td className="px-4 py-2 font-mono text-micro text-steel">{formatDateTime(row.at)}</td>
                    <td className="px-4 py-2 text-caption text-charcoal">
                      {row.actorLabel}
                      <span className="ml-1 font-mono text-micro text-stone">({row.actorType})</span>
                    </td>
                    <td className="px-4 py-2 text-body-sm text-ink">{row.summary}</td>
                    <td className="px-4 py-2 font-mono text-micro text-steel">
                      {row.stateFrom && row.stateTo ? `${row.stateFrom} -> ${row.stateTo}` : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-hairline-soft px-4 py-2 text-caption text-steel">
            {data.items.length} of {data.total} audit events
            {isFetching ? " (refreshing)" : ""}
          </p>
        </div>
      )}
    </div>
  );
}

function ConsentByNoticeVersion() {
  const { data, isError, isPending } = useQuery({
    queryKey: ["audit", { eventType: "candidate_consents" }],
    queryFn: () => fetchAudit({ eventType: "candidate_consents", limit: 200 }),
  });

  if (isPending) return <p role="status" className="text-body-sm text-steel">Loading consent records</p>;
  if (isError) {
    return (
      <p className="rounded-lg border border-hairline-soft bg-canvas p-6 text-center text-body-sm text-steel">
        Could not load consent records.
      </p>
    );
  }

  const counts = new Map<string, number>();
  for (const row of data?.items ?? []) {
    for (const version of noticeVersionsFromPayload(row.payload)) {
      counts.set(version, (counts.get(version) ?? 0) + 1);
    }
  }

  if (counts.size === 0) {
    return (
      <p className="rounded-lg border border-hairline-soft bg-canvas p-6 text-center text-body-sm text-steel">
        No consent records at notice version yet: the backend derives consents from audit
        events and none carry a notice version.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {[...counts.entries()].map(([version, count]) => (
        <li
          key={version}
          className="flex items-center justify-between rounded-lg border border-hairline-soft bg-canvas px-4 py-2.5"
          title="Derived from GET /api/audit?eventType=candidate_consents - folded consent.recorded payload notice_version"
        >
          <span className="font-mono text-body-sm text-ink">{version}</span>
          <span className="text-body-sm text-charcoal">
            {count} consent record{count === 1 ? "" : "s"} at notice version {version}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ErasureRequests() {
  const [candidateId, setCandidateId] = useState("");
  const [reason, setReason] = useState("");
  const [recorded, setRecorded] = useState<ErasureResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () => createErasureRequest({ candidateId: candidateId.trim(), reason: reason.trim() || undefined }),
    onSuccess: (response) => {
      setRecorded(response);
      setSubmitError(null);
      setCandidateId("");
      setReason("");
    },
    onError: (cause) =>
      setSubmitError(cause instanceof ApiError ? cause.message : "Unknown error"),
  });

  return (
    <div>
      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          submit.mutate();
        }}
      >
        <div>
          <label htmlFor="erasure-candidate" className="text-caption font-medium text-charcoal">
            Candidate ID
          </label>
          <input
            id="erasure-candidate"
            type="text"
            required
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
            placeholder="UUID from the candidate journey"
            className="mt-1 h-10 w-full rounded-md border border-hairline bg-canvas px-3 font-mono text-caption text-ink outline-none focus:border-brand-green"
          />
        </div>
        <div>
          <label htmlFor="erasure-reason" className="text-caption font-medium text-charcoal">
            Reason
          </label>
          <input
            id="erasure-reason"
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="GDPR art. 17 request"
            className="mt-1 h-10 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink outline-none focus:border-brand-green"
          />
        </div>
        <button
          type="submit"
          disabled={submit.isPending}
          className="flex h-10 items-center justify-center rounded-full bg-primary px-4 text-body-sm-medium text-on-primary disabled:opacity-50"
        >
          {submit.isPending ? "Submitting..." : "Submit erasure request"}
        </button>
      </form>

      {submitError && (
        <p role="alert" className="mt-3 rounded-sm bg-brand-error/10 px-2 py-1.5 text-caption text-brand-error">
          {submitError}
        </p>
      )}

      {recorded && (
        <div className="mt-3 rounded-lg border border-brand-green bg-brand-green-soft p-3">
          <p className="text-body-sm-medium text-ink">Erasure request recorded</p>
          <p className="mt-1 font-mono text-micro text-charcoal">
            {recorded.id} · candidate {recorded.candidateId} · status {recorded.status} ·{" "}
            {formatDateTime(recorded.requestedAt)}
          </p>
        </div>
      )}

      <p className="mt-3 rounded-lg border border-hairline-soft bg-canvas p-4 text-caption text-steel">
        The backend exposes no list endpoint for erasure requests, so only requests submitted
        in this session show a status here. Past requests live in the audit log.
      </p>
    </div>
  );
}

export function CompliancePage() {
  return (
    <div className="min-w-0">
      <p className="text-micro font-semibold uppercase tracking-wide text-steel">Quality</p>
      <h1 className="text-heading-3 font-semibold text-ink">Compliance</h1>
      <p
        className="mt-2 rounded-lg border border-hairline bg-surface px-3 py-2 text-body-sm text-charcoal"
        role="note"
      >
        DPO view: every action on this page is audited with X-Actor-Role: dpo.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-lg border border-hairline-soft bg-canvas p-4 xl:col-span-2">
          <h2 className="text-heading-5 font-semibold text-ink">Audit log search</h2>
          <div className="mt-3">
            <AuditSearch />
          </div>
        </section>

        <section className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <h2
            className="text-heading-5 font-semibold text-ink"
            title="Derived from GET /api/audit?eventType=candidate_consents"
          >
            Consent records by notice version
          </h2>
          <div className="mt-3">
            <ConsentByNoticeVersion />
          </div>
        </section>

        <section className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <h2
            className="text-heading-5 font-semibold text-ink"
            title="POST /api/erasure-requests with X-Actor-Role: dpo"
          >
            Erasure requests
          </h2>
          <div className="mt-3">
            <ErasureRequests />
          </div>
        </section>

        <section className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <h2 className="text-heading-5 font-semibold text-ink">Data retention countdowns</h2>
          <p className="mt-3 rounded-lg border border-hairline-soft bg-canvas p-6 text-center text-body-sm text-steel">
            Retention countdowns are not exposed by the API yet, so no countdowns are shown
            here.
          </p>
        </section>
      </div>
    </div>
  );
}
