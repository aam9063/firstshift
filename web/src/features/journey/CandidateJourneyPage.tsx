import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { fetchCandidate } from "../../api/client";
import type { CandidateDetail, JourneyStep, RecordRow, ThreadMessage } from "../../api/types";
import { formatDateTime } from "../../lib/dates";

/* Actor colors per specs/04b-console.md section 4.3: agent blue, human orange,
   system steel. Color never carries meaning alone: every chip has a label. */

const AGENT_LABELS: Record<string, string> = {
  recruit: "Recruit",
  onboard: "Onboard",
  pulse: "Pulse",
};

function agentLabel(agentVersion: string): string {
  return AGENT_LABELS[agentVersion.split("@")[0]] ?? agentVersion;
}

function JourneyTimeline({ steps, elapsedLabel }: { steps: JourneyStep[]; elapsedLabel: string }) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-heading-5 font-semibold text-ink">Journey</h2>
        <span className="font-mono text-micro text-stone">{elapsedLabel}</span>
      </div>
      <ol className="mt-3">
        {steps.map((step) => (
          <li key={step.id} className="relative flex gap-3 pb-4 last:pb-0">
            <span
              aria-hidden
              className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${
                step.current ? "bg-brand-green" : "bg-muted"
              }`}
            />
            <div className="min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-body-sm-medium text-ink">{step.label}</span>
                <span className="font-mono text-micro text-stone">{formatDateTime(step.at)}</span>
              </div>
              <p className="text-micro text-steel">
                {step.actorLabel} - {step.note}
              </p>
              {step.current && (
                <span className="mt-1 inline-block rounded-sm bg-brand-green-soft px-1.5 py-0.5 text-micro font-semibold text-ink">
                  Current state
                </span>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ToolCallChip({
  tool,
  argsSummary,
  latencyMs,
  resultSummary,
}: NonNullable<ThreadMessage["toolCalls"]>[number]) {
  return (
    <div className="my-1 rounded-md border border-hairline bg-surface px-2.5 py-1.5">
      <p className="font-mono text-micro text-charcoal">
        {tool}
        {latencyMs ? <span className="text-stone"> + {latencyMs} ms</span> : null}
      </p>
      <p className="font-mono text-micro text-steel">
        {argsSummary}
        {resultSummary ? ` -> ${resultSummary}` : ""}
      </p>
    </div>
  );
}

function Message({ message }: { message: ThreadMessage }) {
  const isCandidate = message.senderType === "candidate";
  return (
    <li className={isCandidate ? "flex flex-col items-start" : "flex flex-col items-end"}>
      <div className="mb-0.5 flex items-center gap-1.5 text-micro text-steel">
        {!isCandidate && message.agentVersion && (
          <span className="font-mono text-brand-tag">{message.agentVersion}</span>
        )}
        <span className="font-mono">{formatDateTime(message.at)}</span>
        {isCandidate && <span className="font-mono">Ines</span>}
      </div>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-body-sm ${
          isCandidate
            ? "bg-surface text-charcoal"
            : "bg-brand-tag/10 text-charcoal"
        }`}
      >
        {message.toolCalls?.map((call) => <ToolCallChip key={call.tool} {...call} />)}
        {message.text.split("\n").map((line, index) => (
          <p key={index} className="whitespace-pre-wrap">
            {line}
          </p>
        ))}
      </div>
    </li>
  );
}

function RecordRowLine({ row }: { row: RecordRow }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-body-sm text-steel">{row.label}</span>
      <span
        className={`text-body-sm ${
          row.status === "not_requested" ? "text-stone" : "text-ink"
        }`}
      >
        {row.value}
      </span>
    </div>
  );
}

function RecordRail({ candidate }: { candidate: CandidateDetail }) {
  return (
    <aside className="flex w-full shrink-0 flex-col gap-4 xl:w-80">
      <section aria-label="Matched shift" className="rounded-lg border border-hairline bg-canvas p-4">
        <p className="text-micro font-semibold uppercase tracking-wide text-steel">Matched shift</p>
        <div className="mt-2 rounded-md border border-brand-green bg-brand-green-soft p-3">
          <p className="text-body-sm-medium text-ink">{candidate.matchedShift.label}</p>
          <p className="mt-1 text-micro text-steel">{candidate.matchedShift.restaurant}</p>
          <p className="mt-1 font-mono text-micro text-steel">
            {candidate.matchedShift.shiftIds.join(" - ")} - held {candidate.matchedShift.held}
          </p>
        </div>
      </section>

      <section aria-label="Summary to manager" className="rounded-lg border border-hairline-soft bg-canvas p-4">
        <p className="text-micro font-semibold uppercase tracking-wide text-steel">
          Summary sent to manager
        </p>
        <div className="mt-1 divide-y divide-hairline-soft">
          {candidate.summaryRows.map((row) => (
            <RecordRowLine key={row.label} row={row} />
          ))}
        </div>
        <p className="mt-2 text-micro text-stone">{candidate.summaryNote}</p>
      </section>

      <section aria-label="Consent" className="rounded-lg border border-hairline-soft bg-canvas p-4">
        <p className="text-micro font-semibold uppercase tracking-wide text-steel">Consent</p>
        <div className="mt-1">
          <RecordRowLine row={candidate.consentRow} />
        </div>
      </section>

      <section aria-label="Pre-boarding" className="rounded-lg border border-hairline-soft bg-canvas p-4">
        <p className="text-micro font-semibold uppercase tracking-wide text-steel">Pre-boarding</p>
        <div className="mt-1 divide-y divide-hairline-soft">
          {candidate.preBoarding.map((row) => (
            <RecordRowLine key={row.label} row={row} />
          ))}
        </div>
      </section>

      <section aria-label="Writes to client systems" className="rounded-lg bg-surface-code p-4">
        <p className="text-micro font-semibold uppercase tracking-wide text-on-dark-muted">
          Writes to client systems
        </p>
        <ul className="mt-2 space-y-2 font-mono text-caption">
          {candidate.writes.map((write) => (
            <li key={write.id}>
              <span className={write.statusCode < 300 ? "text-brand-green" : "text-brand-warn"}>
                {write.statusCode}
              </span>{" "}
              <span className="text-on-dark">{write.target}</span>{" "}
              <span className="text-on-dark-muted">{write.operation}</span>
              <br />
              <span className="text-on-dark-muted">{write.idempotencyKey}</span>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}

export function CandidateJourneyPage() {
  const { id = "" } = useParams();
  const { data: candidate, isLoading } = useQuery({
    queryKey: ["candidate", id],
    queryFn: () => fetchCandidate(id),
  });
  const [thread, setThread] = useState<"candidate" | "manager">("candidate");
  const [inControl, setInControl] = useState<boolean | null>(null);

  if (isLoading || !candidate) {
    return <p className="text-body-sm text-steel">Loading candidate...</p>;
  }

  const humanInControl = inControl ?? !candidate.agentInControl;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-surface text-body-md-medium text-ink">
            {candidate.initials}
          </span>
          <div>
            <h1 className="text-heading-3 font-semibold text-ink">
              {candidate.firstName} {candidate.lastName}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-micro">
              <span className="rounded-full bg-canvas-dark px-2 py-0.5 font-semibold text-on-dark">
                {candidate.stateLabel}
              </span>
              <span className="text-charcoal">{candidate.restaurant}</span>
              {candidate.languages.map((lang) => (
                <span key={lang} className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-steel">
                  {lang}
                </span>
              ))}
              <span className="flex items-center gap-1.5 text-steel">
                <span
                  aria-hidden
                  className={`inline-block h-1.5 w-1.5 rounded-full ${humanInControl ? "bg-testimonial-orange" : "bg-brand-tag"}`}
                />
                {humanInControl ? "Human in control" : `${agentLabel(candidate.agentVersion)} agent in control`}
              </span>
            </div>
          </div>
        </div>
        {humanInControl ? (
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-testimonial-orange/15 px-3 py-1.5 text-body-sm-medium text-ink">
              You are in control
            </span>
            <button
              type="button"
              onClick={() => setInControl(false)}
              className="flex h-9 items-center rounded-full bg-brand-green px-4 text-body-sm-medium text-ink"
            >
              Release to agent
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="flex h-9 items-center rounded-full border border-hairline px-4 text-body-sm-medium text-ink"
            >
              Pause agent
            </button>
            <button
              type="button"
              onClick={() => setInControl(true)}
              className="flex h-9 items-center rounded-full bg-primary px-4 text-body-sm-medium text-on-primary"
            >
              Take over
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-6 xl:flex-row">
        <div className="w-full shrink-0 rounded-lg border border-hairline-soft bg-canvas p-4 xl:w-64">
          <JourneyTimeline steps={candidate.journey} elapsedLabel={candidate.elapsedLabel} />
        </div>

        <div className="min-w-0 flex-1 rounded-lg border border-hairline-soft bg-canvas">
          <div role="tablist" aria-label="Conversation threads" className="flex gap-1 border-b border-hairline-soft px-4 pt-3">
            {(
              [
                ["candidate", "Candidate thread"],
                ["manager", "Manager thread - Yolanda F."],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={thread === key}
                onClick={() => setThread(key)}
                className={`px-3 py-2 text-body-sm-medium ${
                  thread === key
                    ? "border-b-2 border-ink text-ink"
                    : "border-b-2 border-transparent text-steel"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <p className="px-4 pt-2 font-mono text-micro text-steel">
            WhatsApp {candidate.phoneMasked}
          </p>

          <ul className="flex flex-col gap-3 px-4 py-3">
            {(thread === "candidate"
              ? candidate.candidateThread
              : candidate.managerThread
            ).map((message) => (
              <Message key={message.id} message={message} />
            ))}
          </ul>

          <div className="border-t border-hairline-soft p-4">
            {humanInControl ? (
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Type your message as the human in control"
                  className="h-10 flex-1 rounded-md border border-hairline px-3 text-body-sm text-ink outline-none focus:border-brand-green"
                />
                <button
                  type="button"
                  className="h-10 rounded-full bg-primary px-4 text-body-sm-medium text-on-primary"
                >
                  Send
                </button>
              </div>
            ) : (
              <p className="rounded-md bg-surface px-3 py-2 text-body-sm text-steel">
                The {agentLabel(candidate.agentVersion)} agent is replying. Take over to write.
              </p>
            )}
          </div>
        </div>

        <RecordRail candidate={candidate} />
      </div>
    </div>
  );
}
