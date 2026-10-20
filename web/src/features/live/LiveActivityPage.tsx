import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { EventKind, LiveEvent } from "../../api/types";
import { fetchLiveEventsSeed, fetchLiveFeedMeta } from "../../api/client";
import { createMockEventStream } from "../../mocks/mockStream";

const KIND_LABELS: Record<EventKind, string> = {
  agent_turn: "agent.turn",
  tool_call: "tool.call",
  state_change: "state.transition",
  integration: "integration",
  human_action: "human",
};

const KIND_FILTERS: { id: EventKind | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "agent_turn", label: "Agent turns" },
  { id: "tool_call", label: "Tool calls" },
  { id: "state_change", label: "State changes" },
  { id: "integration", label: "Integrations" },
  { id: "human_action", label: "Human actions" },
];

function formatLatency(ms: number): string {
  if (ms >= 60_000) return `${Math.round(ms / 60_000)} min`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)} s`;
  return `${ms} ms`;
}

function actorColor(type: LiveEvent["actorType"]): string {
  if (type === "agent") return "bg-brand-tag";
  if (type === "human") return "bg-testimonial-orange";
  return "bg-steel";
}

function EventDetail({ event }: { event: LiveEvent }) {
  return (
    <div className="grid gap-4 border-t border-hairline-soft bg-surface-soft/60 px-4 py-4 md:grid-cols-[220px_1fr]">
      <dl className="space-y-2 text-body-sm">
        <div>
          <dt className="text-steel">Prompt</dt>
          <dd className="font-mono text-charcoal">{event.agentVersion ?? "-"}</dd>
        </div>
        <div>
          <dt className="text-steel">Model</dt>
          <dd className="font-mono text-charcoal">{event.model ?? "-"}</dd>
        </div>
        <div>
          <dt className="text-steel">State</dt>
          <dd className="font-mono text-charcoal">{event.state ?? "-"}</dd>
        </div>
        <div>
          <dt className="text-steel">Tokens</dt>
          <dd className="font-mono text-charcoal">
            {event.tokensIn ? `${event.tokensIn.toLocaleString("en-US")} in - ${event.tokensOut} out` : "-"}
          </dd>
        </div>
        <div>
          <dt className="text-steel">Validation</dt>
          <dd className="text-charcoal">{event.validation ?? "-"}</dd>
        </div>
        <div>
          <dt className="text-steel">Trace</dt>
          <dd className="font-mono text-charcoal">{event.traceId ?? "-"}</dd>
        </div>
      </dl>
      {event.toolCall && (
        <div>
          <div className="flex items-center justify-between rounded-md bg-surface-code px-3 py-2">
            <span className="font-mono text-caption text-on-dark">
              {event.toolCall.tool} - arguments and result
            </span>
            <button
              type="button"
              className="rounded-sm border border-hairline-dark px-2 py-0.5 font-mono text-micro text-on-dark-muted"
            >
              Copy
            </button>
          </div>
          <pre className="overflow-x-auto rounded-md rounded-t-none bg-surface-code p-3 font-mono text-caption text-on-dark">
{`${event.toolCall.argumentsJson}\n\n->\n\n${event.toolCall.resultJson}`}
          </pre>
        </div>
      )}
      <div className="flex gap-2 md:col-span-2">
        <Link
          to={`/candidates/${event.summary.match(/C-\d{4}/)?.[0] ?? ""}`}
          className="flex h-9 items-center rounded-full bg-primary px-4 text-body-sm-medium text-on-primary"
        >
          Open candidate journey
        </Link>
        <button
          type="button"
          className="flex h-9 items-center rounded-full border border-hairline px-4 text-body-sm-medium text-ink"
        >
          View trace
        </button>
      </div>
    </div>
  );
}

export function LiveActivityPage() {
  const { data: meta } = useQuery({ queryKey: ["live-feed-meta"], queryFn: fetchLiveFeedMeta });
  const { data: seed } = useQuery({ queryKey: ["live-events-seed"], queryFn: fetchLiveEventsSeed });

  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<EventKind | "all">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const streamRef = useRef<ReturnType<typeof createMockEventStream> | null>(null);

  useEffect(() => {
    streamRef.current?.[paused ? "pause" : "resume"]();
  }, [paused]);

  const seededRef = useRef(false);
  useEffect(() => {
    if (seed && !seededRef.current) {
      seededRef.current = true;
      setEvents(seed);
    }
  }, [seed]);

  useEffect(() => {
    if (!seed) return;
    let counter = 0;
    const stream = createMockEventStream({
      events: seed,
      intervalMs: 7500,
      loop: true,
      onEvent: (event) => {
        counter += 1;
        setEvents((current) => [
          { ...event, id: `${event.id}-replay-${counter}` },
          ...current,
        ]);
      },
    });
    streamRef.current = stream;
    stream.start();
    return () => stream.stop();
  }, [seed]);

  const visible = useMemo(
    () => (filter === "all" ? events : events.filter((event) => event.kind === filter)),
    [events, filter],
  );

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const event of events) {
      map.set(event.kind, (map.get(event.kind) ?? 0) + 1);
    }
    return map;
  }, [events]);

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
      <div className="min-w-0">
        <p className="font-mono text-micro uppercase tracking-wide text-steel">
          Event stream - SSE
        </p>
        <h1 className="text-heading-3 font-semibold text-ink">Live agent activity</h1>
        <p className="mt-1 text-body-sm text-steel">
          Every turn, tool call, state change and write to a client system, as it happens.
        </p>

        <div className="mt-4 flex items-center gap-3">
          <span className="flex items-center gap-2 rounded-full bg-brand-green-soft px-3 py-1.5 text-body-sm-medium text-ink">
            <span
              aria-hidden
              className={`inline-block h-1.5 w-1.5 rounded-full bg-brand-green ${paused ? "" : "animate-pulse"}`}
            />
            {paused ? "Paused" : "Streaming"} - {events.length} events
          </span>
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            className="flex h-9 items-center rounded-full border border-hairline px-4 text-body-sm-medium text-ink"
          >
            {paused ? "Resume feed" : "Pause feed"}
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Filter by event kind">
          {KIND_FILTERS.map((option) => (
            <button
              key={option.id}
              type="button"
              role="tab"
              aria-selected={filter === option.id}
              onClick={() => setFilter(option.id)}
              className={`flex h-8 items-center gap-1.5 rounded-full border px-3 text-body-sm-medium ${
                filter === option.id
                  ? "border-primary bg-primary text-on-primary"
                  : "border-hairline bg-canvas text-steel"
              }`}
            >
              {option.label}
              <span className="font-mono text-micro">
                {option.id === "all"
                  ? events.length
                  : (counts.get(option.id) ?? 0)}
              </span>
            </button>
          ))}
        </div>

        <div className="mt-4 overflow-hidden rounded-lg border border-hairline-soft bg-canvas">
          <div className="grid grid-cols-[80px_110px_130px_1fr_80px] gap-2 border-b border-hairline-soft px-4 py-2 text-micro font-semibold uppercase tracking-wide text-steel">
            <span>Time</span>
            <span>Actor</span>
            <span>Event</span>
            <span>What happened</span>
            <span className="text-right">Latency</span>
          </div>
          <ul>
            {visible.map((event) => {
              const expanded = expandedId === event.id;
              return (
                <li key={event.id} className="border-b border-hairline-soft last:border-b-0">
                  <button
                    type="button"
                    onClick={() => setExpandedId(expanded ? null : event.id)}
                    aria-expanded={expanded}
                    className="grid w-full grid-cols-[80px_110px_130px_1fr_80px] items-center gap-2 px-4 py-2.5 text-left hover:bg-surface"
                  >
                    <span className="font-mono text-micro text-stone">{event.at}</span>
                    <span className="flex items-center gap-1.5 text-body-sm text-charcoal">
                      <span aria-hidden className={`inline-block h-1.5 w-1.5 rounded-full ${actorColor(event.actorType)}`} />
                      {event.actorLabel}
                    </span>
                    <span className="font-mono text-micro text-steel">{KIND_LABELS[event.kind]}</span>
                    <span className="truncate text-body-sm text-ink">{event.summary}</span>
                    <span className="text-right font-mono text-micro text-stone">
                      {event.latencyMs ? formatLatency(event.latencyMs) : ""}
                    </span>
                  </button>
                  {expanded && <EventDetail event={event} />}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      <aside className="flex flex-col gap-4">
        <section aria-label="Health" className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <p className="text-micro font-semibold uppercase tracking-wide text-steel">
            {meta?.health.windowLabel ?? "Last hour"}
          </p>
          <dl className="mt-2 space-y-2 text-body-sm">
            <div className="flex justify-between">
              <dt className="text-steel">p95 reply latency</dt>
              <dd className="font-mono text-ink">{meta?.health.p95ReplyLatency ?? "-"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-steel">Schema re-asks</dt>
              <dd className="font-mono text-ink">{meta?.health.schemaReasks ?? "-"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-steel">LLM errors</dt>
              <dd className="font-mono text-ink">{meta?.health.llmErrors ?? "-"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-steel">Outbox in DLQ</dt>
              <dd className="font-mono text-ink">{meta?.health.outboxInDlq ?? "-"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-steel">Cost per hire</dt>
              <dd className="font-mono text-ink">{meta?.health.costPerHire ?? "-"}</dd>
            </div>
          </dl>
        </section>

        <section aria-label="Agents" className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <p className="text-micro font-semibold uppercase tracking-wide text-steel">Agents</p>
          <ul className="mt-2 space-y-2">
            {meta?.agents.map((agent) => (
              <li key={agent.id} className="flex items-center gap-2 text-body-sm">
                <input type="checkbox" defaultChecked className="h-3.5 w-3.5 accent-[rgb(16_16_16)]" />
                <span className="text-ink">{agent.label}</span>
                <span className="ml-auto font-mono text-micro text-steel">{agent.version}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="Guardrails" className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <p className="text-micro font-semibold uppercase tracking-wide text-steel">Guardrails</p>
          <ul className="mt-2 space-y-2">
            {meta?.guardrails.map((rule) => (
              <li key={rule.id} className="flex items-start gap-2 text-body-sm">
                <span
                  aria-hidden
                  className={`mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${rule.ok ? "bg-brand-green" : "bg-testimonial-orange"}`}
                />
                <span className="text-charcoal">{rule.label}</span>
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  );
}
