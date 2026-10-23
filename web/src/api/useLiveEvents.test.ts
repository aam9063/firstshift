/* Live SSE hook contract (odd/tasks/console-live.md T2/S2): one EventSource
   on GET /api/events/stream, envelopes mapped to LiveEvent kinds, reconnect
   carrying the Last-Event-ID cursor, pause/resume gating rendering. */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { envelopeToLiveEvent, useLiveEvents, type StreamEnvelope } from "./useLiveEvents";

/* Minimal EventSource stand-in: no network, dispatches what the test emits
   and records every instance so reconnects can be asserted. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static reset() {
    FakeEventSource.instances = [];
  }

  url: string;
  readyState = 0;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  private listeners = new Map<string, ((event: { data?: string }) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: { data?: string }) => void) {
    const list = this.listeners.get(type) ?? [];
    list.push(handler);
    this.listeners.set(type, list);
  }

  removeEventListener(type: string, handler: (event: { data?: string }) => void) {
    this.listeners.set(type, (this.listeners.get(type) ?? []).filter((h) => h !== handler));
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }

  /* test helpers */
  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  emit(type: string, envelope: StreamEnvelope) {
    const event = { data: JSON.stringify(envelope) };
    const named = this.listeners.get(type) ?? [];
    if (named.length > 0) {
      // Real EventSource dispatches named events only to their listeners.
      for (const handler of named) handler(event);
    } else {
      // Unnamed event types fall through to the default "message" handler.
      this.onmessage?.(event as { data: string });
    }
  }

  fail() {
    this.onerror?.();
  }
}

function envelope(overrides: Partial<StreamEnvelope> = {}): StreamEnvelope {
  return {
    event_id: "11111111-1111-4111-8111-111111111111",
    type: "state.transition",
    occurred_at: "2026-10-22T09:05:54.771188+00:00",
    candidate_id: null,
    trace_id: "tr_1",
    payload: {},
    ...overrides,
  };
}

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useLiveEvents", () => {
  it("opens one EventSource on /api/events/stream and maps envelopes to LiveEvent kinds", async () => {
    const { result } = renderHook(() => useLiveEvents());

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.instances[0].url).toBe("http://localhost:8001/api/events/stream");
    FakeEventSource.instances[0].open();

    FakeEventSource.instances[0].emit(
      "agent.turn",
      envelope({
        type: "agent.turn",
        event_id: "a-1",
        payload: {
          agent: "recruit",
          prompt_version: "v7",
          model: "gpt-4.1-mini",
          state: "screening",
          status: "ok",
          latency_ms: 412.4,
          tokens: { input: 1842, output: 214 },
          validation_retries: 0,
        },
      }),
    );
    FakeEventSource.instances[0].emit(
      "tool.call",
      envelope({ type: "tool.call", event_id: "t-1", payload: { agent: "onboard", tool: "get_open_shifts", status: "ok", result: { shifts: ["S-1"] }, state: "screening" } }),
    );
    FakeEventSource.instances[0].emit(
      "state.transition",
      envelope({
        event_id: "s-1",
        payload: { actor_kind: "candidate", actor_name: "Alberto", from_state: "contacted", to_state: "consented" },
      }),
    );
    FakeEventSource.instances[0].emit(
      "integration.write",
      envelope({ type: "integration.write", event_id: "i-1", payload: { port: "hiredesk", operation: "interview_scheduled" } }),
    );
    FakeEventSource.instances[0].emit(
      "message.out",
      envelope({ type: "message.out", event_id: "m-1", payload: { sender_type: "human", role: "Yolanda F.", body: "decision: book_interview" } }),
    );

    await waitFor(() => expect(result.current.events).toHaveLength(5));
    const kinds = result.current.events.map((event) => event.kind);
    // newest first: the stream prepends
    expect(kinds).toEqual(["human_action", "integration", "state_change", "tool_call", "agent_turn"]);
    const agentTurn = result.current.events[4];
    expect(agentTurn.actorType).toBe("agent");
    expect(agentTurn.actorLabel).toBe("Recruit");
    expect(agentTurn.agentVersion).toBe("recruit@v7");
    expect(agentTurn.model).toBe("gpt-4.1-mini");
    expect(agentTurn.latencyMs).toBe(412);
    expect(agentTurn.tokensIn).toBe(1842);
    expect(agentTurn.tokensOut).toBe(214);
    expect(agentTurn.state).toBe("screening");
    const integration = result.current.events[1];
    expect(integration.summary).toBe("write hiredesk interview_scheduled");
    const human = result.current.events[0];
    expect(human.actorType).toBe("human");
    expect(human.actorLabel).toBe("Yolanda F.");
  });

  it("maps every documented envelope type plus a human_action fallback for the rest", () => {
    expect(envelopeToLiveEvent(envelope({ type: "message.in", payload: { role: "candidate", text: "hola" } })).kind).toBe("human_action");
    expect(envelopeToLiveEvent(envelope({ type: "unmatched.inbound" })).kind).toBe("human_action");
    expect(envelopeToLiveEvent(envelope({ type: "escalation.created" })).kind).toBe("human_action");
    const unknown = envelopeToLiveEvent(envelope({ type: "something.new", payload: { reason: "x" } }));
    expect(unknown.kind).toBe("human_action");
    expect(unknown.summary).toBe("something.new");
  });

  it("reconnects after an error and carries the Last-Event-ID cursor", async () => {
    const { result } = renderHook(() => useLiveEvents({ reconnectMs: 20 }));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const first = FakeEventSource.instances[0];
    first.open();
    first.emit(
      "state.transition",
      envelope({ event_id: "e-42", occurred_at: "2026-10-22T09:06:39.234290+00:00" }),
    );
    await waitFor(() => expect(result.current.events).toHaveLength(1));

    act(() => first.fail());

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2));
    expect(first.closed).toBe(true);
    const second = FakeEventSource.instances[1];
    expect(second.url).toContain(
      `last_event_id=${encodeURIComponent("2026-10-22T09:06:39.234290+00:00|e-42")}`,
    );
    second.open();
    second.emit(
      "state.transition",
      envelope({ event_id: "e-43", occurred_at: "2026-10-22T09:07:00.000000+00:00" }),
    );
    await waitFor(() => expect(result.current.events).toHaveLength(2));
    expect(result.current.events[0].id).toBe("e-43");
  });

  it("stops rendering events while paused and resumes afterwards", async () => {
    const { result } = renderHook(() => useLiveEvents());
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.open();
    source.emit("state.transition", envelope({ event_id: "p-1" }));
    await waitFor(() => expect(result.current.events).toHaveLength(1));

    act(() => result.current.setPaused(true));
    source.emit("state.transition", envelope({ event_id: "p-2" }));
    expect(result.current.events).toHaveLength(1);
    expect(result.current.paused).toBe(true);

    act(() => result.current.setPaused(false));
    source.emit("state.transition", envelope({ event_id: "p-3" }));
    await waitFor(() => expect(result.current.events).toHaveLength(2));
    expect(result.current.events[0].id).toBe("p-3");
  });

  it("closes the EventSource on unmount", async () => {
    const { unmount } = renderHook(() => useLiveEvents());
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    unmount();
    expect(source.closed).toBe(true);
  });
});
