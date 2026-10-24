import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  advanceSimClock,
  ApiError,
  fetchSimulatorMessages,
  loadSimScenario,
  sendSimMessage,
} from "../../api/client";
import type { SimulatorMessage } from "../../api/types";
import { useLiveEvents } from "../../api/useLiveEvents";
import { formatDateTime } from "../../lib/dates";

/* Simulator (specs/04b-console.md section 3.9, odd/tasks/console-views.md
   T5/S5): three panes (candidate phone, manager phone from the same outbound
   feed filtered by recipient, live timeline from the SSE hook), the scenario
   loader D1-D7, clock controls (+1 h, +1 day, next timer) and a candidate or
   manager composer. Quick replies render as real buttons and send as the
   candidate, exactly as they would in WhatsApp. */

const SCENARIOS = ["D1", "D2", "D3", "D4", "D5", "D6", "D7"] as const;

/* The channel feed is one list per recipient: the first recipient (whoever
   received the first outbound message) is the candidate thread, any other
   recipient is the manager thread. */
function splitThreads(messages: SimulatorMessage[]): {
  candidate: SimulatorMessage[];
  manager: SimulatorMessage[];
  candidateRef: string | null;
  managerRef: string | null;
} {
  const candidateRef = messages[0]?.recipientRef ?? null;
  const managerRef =
    messages.find((message) => message.recipientRef !== candidateRef)?.recipientRef ?? null;
  return {
    candidate: messages.filter((message) => message.recipientRef === candidateRef),
    manager: messages.filter((message) => message.recipientRef !== candidateRef),
    candidateRef,
    managerRef,
  };
}

function Bubble({ message }: { message: SimulatorMessage }) {
  return (
    <div className="max-w-[85%] rounded-lg bg-brand-green-soft px-3 py-2">
      <p className="text-body-sm text-ink">{message.body}</p>
    </div>
  );
}

function PhonePane({
  title,
  subtitle,
  messages,
  emptyText,
  children,
}: {
  title: string;
  subtitle: string;
  messages: SimulatorMessage[];
  emptyText: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-hairline-soft bg-canvas p-4">
      <h2 className="text-heading-5 font-semibold text-ink">{title}</h2>
      <p className="font-mono text-micro text-stone" title={subtitle}>
        {subtitle}
      </p>
      <div className="mt-3 flex-1 space-y-2 overflow-y-auto">
        {messages.length === 0 ? (
          <p className="text-body-sm text-steel">{emptyText}</p>
        ) : (
          messages.map((message, index) => <Bubble key={index} message={message} />)
        )}
      </div>
      {children}
    </section>
  );
}

function TimelinePane() {
  const { events, connected } = useLiveEvents();
  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-hairline-soft bg-canvas p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-heading-5 font-semibold text-ink">Live timeline</h2>
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${connected ? "bg-brand-green" : "bg-brand-error"}`}
          aria-label={connected ? "stream connected" : "stream disconnected"}
        />
      </div>
      <p className="font-mono text-micro text-stone" title="GET /api/events/stream (SSE)">
        GET /api/events/stream (SSE)
      </p>
      <ul className="mt-3 flex-1 space-y-1.5 overflow-y-auto">
        {events.length === 0 ? (
          <li className="text-body-sm text-steel">Waiting for events from the scenario run.</li>
        ) : (
          events.map((event) => (
            <li key={event.id} className="border-b border-hairline-soft pb-1.5 last:border-b-0">
              <p className="text-caption text-charcoal">
                <span className="font-mono text-micro text-steel">{formatDateTime(event.at)} </span>
                {event.summary}
              </p>
              <p className="font-mono text-micro text-stone">{event.actorLabel}</p>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}

export function SimulatorPage() {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [runState, setRunState] = useState<string | null>(null);
  const [managerName, setManagerName] = useState<string | null>(null);
  const [composerRole, setComposerRole] = useState<"candidate" | "manager">("candidate");
  const [composerText, setComposerText] = useState("");

  const messagesQuery = useQuery({
    queryKey: ["simulator", "messages"],
    queryFn: fetchSimulatorMessages,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["simulator", "messages"] });

  const loadScenario = useMutation({
    mutationFn: (scenarioId: string) => loadSimScenario(scenarioId),
    onSuccess: (response) => {
      setActionError(null);
      setRunState(response.state);
      setManagerName(
        typeof response.manager?.name === "string" ? response.manager.name : null,
      );
      refresh();
    },
    onError: (cause) =>
      setActionError(cause instanceof ApiError ? cause.message : "Unknown error"),
  });

  const advance = useMutation({
    mutationFn: advanceSimClock,
    onSuccess: (response) => {
      setActionError(null);
      setRunState(response.state);
      refresh();
    },
    onError: (cause) =>
      setActionError(cause instanceof ApiError ? cause.message : "Unknown error"),
  });

  const send = useMutation({
    mutationFn: (input: { role: "candidate" | "manager"; text: string }) =>
      sendSimMessage(input),
    onSuccess: () => {
      setActionError(null);
      refresh();
    },
    onError: (cause) =>
      setActionError(cause instanceof ApiError ? cause.message : "Unknown error"),
  });

  const threads = splitThreads(messagesQuery.data ?? []);
  const lastCandidateMessage = threads.candidate[threads.candidate.length - 1];
  const quickReplies = lastCandidateMessage?.quickReplies ?? [];

  const compose = (role: "candidate" | "manager", text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    send.mutate({ role, text: trimmed });
  };

  return (
    <div className="flex min-w-0 flex-col">
      <p className="text-micro font-semibold uppercase tracking-wide text-steel">Operations</p>
      <h1 className="text-heading-3 font-semibold text-ink">Simulator</h1>
      <p className="mt-1 text-body-sm text-steel">
        Drive the demo scenarios D1-D7 from the simulated channel, exactly as the messages
        would arrive in WhatsApp.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-caption font-medium text-charcoal">Scenario</span>
        {SCENARIOS.map((scenarioId) => (
          <button
            key={scenarioId}
            type="button"
            onClick={() => loadScenario.mutate(scenarioId)}
            disabled={loadScenario.isPending}
            className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink disabled:opacity-50"
            title={`POST /api/sim/scenarios/${scenarioId}/load - resets the run and fires the HireDesk webhook`}
          >
            {scenarioId}
          </button>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-caption font-medium text-charcoal">Clock</span>
        <button
          type="button"
          onClick={() => advance.mutate({ hours: 1 })}
          disabled={advance.isPending}
          className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink disabled:opacity-50"
          title="POST /api/sim/clock/advance { hours: 1 }"
        >
          +1 h
        </button>
        <button
          type="button"
          onClick={() => advance.mutate({ days: 1 })}
          disabled={advance.isPending}
          className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink disabled:opacity-50"
          title="POST /api/sim/clock/advance { days: 1 }"
        >
          +1 day
        </button>
        <button
          type="button"
          onClick={() => advance.mutate({ next_timer: true })}
          disabled={advance.isPending}
          className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink disabled:opacity-50"
          title="POST /api/sim/clock/advance { next_timer: true } - jump to the next pending timer and fire it"
        >
          Next timer
        </button>
        {runState && (
          <span className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-micro text-steel">
            state: {runState}
            {managerName ? ` · manager: ${managerName}` : ""}
          </span>
        )}
      </div>

      {actionError && (
        <p role="alert" className="mt-2 rounded-sm bg-brand-error/10 px-2 py-1.5 text-caption text-brand-error">
          {actionError}
        </p>
      )}

      <div className="mt-4 grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="flex min-h-0 flex-col gap-4">
          <PhonePane
            title="Candidate phone"
            subtitle={
              threads.candidateRef
                ? `outbound to ${threads.candidateRef}`
                : "GET /simulator/messages"
            }
            messages={threads.candidate}
            emptyText="Load a scenario to see the conversation the agent sends to the candidate."
          >
            {quickReplies.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-hairline-soft pt-3">
                <span className="text-caption font-medium text-charcoal">Quick replies</span>
                {quickReplies.map((reply) => (
                  <button
                    key={reply}
                    type="button"
                    onClick={() => compose("candidate", reply)}
                    className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink"
                    title="POST /api/sim/messages as the candidate"
                  >
                    {reply}
                  </button>
                ))}
              </div>
            )}
          </PhonePane>

          <PhonePane
            title="Manager phone"
            subtitle={
              threads.managerRef
                ? `outbound to ${threads.managerRef}`
                : "GET /simulator/messages - no manager thread yet"
            }
            messages={threads.manager}
            emptyText="No manager messages in this run yet: the manager is messaged when a shift proposal needs a decision."
          />
        </div>

        <TimelinePane />
      </div>

      <form
        className="mt-4 rounded-lg border border-hairline-soft bg-canvas p-4"
        onSubmit={(event) => {
          event.preventDefault();
          compose(composerRole, composerText);
          setComposerText("");
        }}
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div>
            <label htmlFor="sim-role" className="text-caption font-medium text-charcoal">
              Send as
            </label>
            <select
              id="sim-role"
              value={composerRole}
              onChange={(event) =>
                setComposerRole(event.target.value as "candidate" | "manager")
              }
              className="mt-1 block h-10 rounded-md border border-hairline bg-canvas px-2 text-body-sm text-ink"
            >
              <option value="candidate">Candidate</option>
              <option value="manager">Manager</option>
            </select>
          </div>
          <div className="flex-1">
            <label htmlFor="sim-message" className="text-caption font-medium text-charcoal">
              Message
            </label>
            <input
              id="sim-message"
              type="text"
              value={composerText}
              onChange={(event) => setComposerText(event.target.value)}
              placeholder="Escribe como el candidato o el manager..."
              className="mt-1 h-10 w-full rounded-md border border-hairline bg-canvas px-3 text-body-sm text-ink outline-none focus:border-brand-green"
            />
          </div>
          <button
            type="submit"
            disabled={send.isPending}
            className="flex h-10 items-center justify-center rounded-full bg-primary px-4 text-body-sm-medium text-on-primary disabled:opacity-50"
            title="POST /api/sim/messages"
          >
            {send.isPending ? "Sending..." : "Send message"}
          </button>
        </div>
      </form>
    </div>
  );
}
