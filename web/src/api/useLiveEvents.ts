import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "./client";
import type { ActorType, EventKind, LiveEvent } from "./types";

/* Real SSE replacement for the scripted stream (odd/tasks/console-live.md
   T2, specs/04b-console.md sections 1 and 3.2). One EventSource on
   GET /api/events/stream; every persisted typed event arrives as an
   envelope and is mapped to a LiveEvent for the feed:

     agent.turn        -> agent_turn
     tool.call         -> tool_call
     state.transition  -> state_change
     integration.write -> integration
     human and audit rows (message.in/out, unmatched.inbound,
     escalation.created, unknown types) -> human_action

   Reconnect: the backend accepts the stream cursor both as the standard
   Last-Event-ID header (set by browsers) and as a last_event_id query
   parameter; the hook sends the query form so the cursor survives a
   manual reconnect and is testable (app/api/events_stream.py). Pause only
   gates rendering: the connection stays open and the cursor keeps
   advancing, so nothing is missed and nothing is duplicated. */

const STREAM_URL = `${API_URL}/api/events/stream`;
const RECONNECT_MS = 1000;
const EXCERPT_LIMIT = 100;

export interface StreamEnvelope {
  event_id: string;
  type: string;
  occurred_at: string;
  candidate_id: string | null;
  trace_id: string | null;
  payload: Record<string, unknown>;
}

interface UseLiveEventsOptions {
  /** Delay before reopening after an error; tests pass a small value. */
  reconnectMs?: number;
}

export interface UseLiveEventsResult {
  events: LiveEvent[];
  paused: boolean;
  setPaused: (paused: boolean) => void;
  connected: boolean;
}

function str(payload: Record<string, unknown>, key: string): string {
  return typeof payload[key] === "string" ? (payload[key] as string) : "";
}

function excerpt(text: string): string {
  const flat = text.split(/\s+/).filter(Boolean).join(" ");
  if (flat.length <= EXCERPT_LIMIT) return flat;
  return `${flat.slice(0, EXCERPT_LIMIT - 3).trimEnd()}...`;
}

function clockUtc(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
}

function kindFor(type: string): EventKind {
  switch (type) {
    case "agent.turn":
      return "agent_turn";
    case "tool.call":
      return "tool_call";
    case "state.transition":
      return "state_change";
    case "integration.write":
      return "integration";
    default:
      // Human and audit rows and anything unrecognized land here so every
      // envelope still maps to a LiveEvent (feature doc S2).
      return "human_action";
  }
}

function actorFromKind(kind: string): { actorType: ActorType; actorLabel: string } {
  if (kind === "candidate") return { actorType: "candidate", actorLabel: "Candidate" };
  if (kind === "human") return { actorType: "human", actorLabel: "Staff" };
  if (kind === "agent") return { actorType: "agent", actorLabel: "FirstShift agent" };
  return { actorType: "system", actorLabel: "System" };
}

function agentLabel(agent: string): string {
  return toTitleCase(agent);
}

function toTitleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/* Maps one stream envelope to the LiveEvent shape the feed renders. The
   presentation rules mirror the backend's activity mapping in
   app/api/console/overview.py (_event_activity) so both views tell the
   same story from the same events. */
export function envelopeToLiveEvent(envelope: StreamEnvelope): LiveEvent {
  const payload = envelope.payload ?? {};
  const kind = kindFor(envelope.type);
  let actorType: ActorType = "system";
  let actorLabel = "FirstShift";
  let summary = envelope.type;
  const event: LiveEvent = {
    id: envelope.event_id,
    kind,
    actorType,
    actorLabel,
    summary,
    at: clockUtc(envelope.occurred_at),
    traceId: envelope.trace_id ?? undefined,
  };

  switch (envelope.type) {
    case "agent.turn": {
      const agent = agentLabel(str(payload, "agent"));
      actorType = "agent";
      actorLabel = agent;
      const state = str(payload, "state");
      const status = str(payload, "status") || "ok";
      summary = `${agent} agent turn in ${state} (${status})`;
      const promptVersion = str(payload, "prompt_version");
      if (promptVersion) event.agentVersion = `${str(payload, "agent")}@${promptVersion}`;
      event.model = str(payload, "model") || undefined;
      event.state = state || undefined;
      event.latencyMs =
        typeof payload.latency_ms === "number" ? Math.round(payload.latency_ms) : undefined;
      const tokens = payload.tokens as { input?: number; output?: number } | undefined;
      event.tokensIn = tokens?.input;
      event.tokensOut = tokens?.output;
      const retries = typeof payload.validation_retries === "number" ? payload.validation_retries : 0;
      event.validation = retries > 0 ? `${retries} schema re-asks` : undefined;
      break;
    }
    case "tool.call": {
      const tool = str(payload, "tool");
      const status = str(payload, "status");
      actorType = "agent";
      actorLabel = agentLabel(str(payload, "agent"));
      summary = status ? `tool ${tool} (${status})` : `tool ${tool}`;
      event.toolCall = {
        tool,
        argumentsJson: JSON.stringify(payload.arguments ?? {}, null, 2),
        resultJson: JSON.stringify(payload.result ?? { reason: payload.reason }, null, 2),
      };
      break;
    }
    case "state.transition": {
      const derived = actorFromKind(str(payload, "actor_kind"));
      actorType = derived.actorType;
      actorLabel = str(payload, "actor_name") || derived.actorLabel;
      const from = str(payload, "from_state");
      const to = str(payload, "to_state");
      summary = from ? `${from} -> ${to}` : `entered ${to}`;
      event.state = to || undefined;
      break;
    }
    case "integration.write": {
      const port = str(payload, "port");
      const operation = str(payload, "operation");
      summary = `write ${port} ${operation}`.trim();
      break;
    }
    case "message.out": {
      if (str(payload, "sender_type") === "human") {
        actorType = "human";
        actorLabel = str(payload, "role") || "Staff";
      } else {
        actorType = "agent";
      }
      summary = excerpt(str(payload, "body"));
      break;
    }
    case "message.in": {
      const role = str(payload, "role") || "candidate";
      if (role === "manager") {
        actorType = "human";
        actorLabel = "Manager";
      } else if (role === "system") {
        actorType = "system";
        actorLabel = "HireDesk";
      } else {
        actorType = "candidate";
        actorLabel = "Candidate";
      }
      summary = excerpt(str(payload, "text") || str(payload, "body"));
      break;
    }
    case "unmatched.inbound": {
      actorType = "candidate";
      actorLabel = str(payload, "profile_name") || str(payload, "from") || "Unknown";
      summary = `Unmatched message from ${str(payload, "from")}`;
      break;
    }
    case "escalation.created": {
      summary = excerpt(str(payload, "reason") || "escalated to a human");
      break;
    }
    default:
      break;
  }

  event.actorType = actorType;
  event.actorLabel = actorLabel;
  event.summary = summary;
  return event;
}

export function useLiveEvents(options: UseLiveEventsOptions = {}): UseLiveEventsResult {
  const reconnectMs = options.reconnectMs ?? RECONNECT_MS;
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [paused, setPausedState] = useState(false);
  const [connected, setConnected] = useState(false);
  const pausedRef = useRef(paused);
  const cursorRef = useRef<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const setPaused = useCallback((value: boolean) => {
    pausedRef.current = value;
    setPausedState(value);
  }, []);

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const handleEnvelope = (raw: string) => {
      let envelope: StreamEnvelope;
      try {
        envelope = JSON.parse(raw) as StreamEnvelope;
      } catch {
        return; // a malformed frame never reaches the feed
      }
      cursorRef.current = `${envelope.occurred_at}|${envelope.event_id}`;
      if (pausedRef.current) return;
      const event = envelopeToLiveEvent(envelope);
      setEvents((current) => [event, ...current]);
    };

    const connect = () => {
      if (disposed) return;
      const url = cursorRef.current
        ? `${STREAM_URL}?last_event_id=${encodeURIComponent(cursorRef.current)}`
        : STREAM_URL;
      const source = new EventSource(url);
      sourceRef.current = source;

      source.onopen = () => setConnected(true);
      source.onerror = () => {
        setConnected(false);
        source.close();
        if (disposed) return;
        reconnectTimer = setTimeout(connect, reconnectMs);
      };
      // Named SSE events carry the envelope; "message" catches any type the
      // backend adds before this hook learns its name.
      source.onmessage = (event) => handleEnvelope((event as MessageEvent).data);
      for (const type of [
        "agent.turn",
        "tool.call",
        "state.transition",
        "integration.write",
        "message.in",
        "message.out",
        "unmatched.inbound",
        "escalation.created",
      ]) {
        source.addEventListener(type, (event) =>
          handleEnvelope((event as MessageEvent).data),
        );
      }
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      sourceRef.current?.close();
      sourceRef.current = null;
      setConnected(false);
    };
  }, [reconnectMs]);

  return { events, paused, setPaused, connected };
}
