import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { createMockEventStream } from "./mockStream";
import type { LiveEvent } from "../api/types";

const events: LiveEvent[] = [
  {
    id: "evt-1",
    kind: "agent_turn",
    actorType: "agent",
    actorLabel: "Recruit",
    agentVersion: "recruit@v7",
    summary: "Declined an off-policy request and stayed in scope",
    at: "21:41:12",
    latencyMs: 1600,
  },
  {
    id: "evt-2",
    kind: "tool_call",
    actorType: "agent",
    actorLabel: "Onboard",
    agentVersion: "onboard@v4",
    summary: "Food hygiene module completed by C-0177",
    at: "21:40:12",
    latencyMs: 236,
  },
  {
    id: "evt-3",
    kind: "integration",
    actorType: "system",
    actorLabel: "System",
    summary: "Outbox retry 2 of 5 to Nomina360 OUT-4471",
    at: "21:39:46",
    latencyMs: 60200,
  },
];

describe("createMockEventStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("emits events in order on its interval", () => {
    const onEvent = vi.fn();
    const stream = createMockEventStream({ events, intervalMs: 100, onEvent });
    stream.start();

    vi.advanceTimersByTime(100);
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenLastCalledWith(events[0]);

    vi.advanceTimersByTime(200);
    expect(onEvent).toHaveBeenCalledTimes(3);
    expect(onEvent).toHaveBeenLastCalledWith(events[2]);
    stream.stop();
  });

  it("does not emit while paused and resumes where it stopped", () => {
    const onEvent = vi.fn();
    const stream = createMockEventStream({ events, intervalMs: 100, onEvent });
    stream.start();

    vi.advanceTimersByTime(100);
    expect(onEvent).toHaveBeenCalledTimes(1);

    stream.pause();
    vi.advanceTimersByTime(500);
    expect(onEvent).toHaveBeenCalledTimes(1);

    stream.resume();
    vi.advanceTimersByTime(100);
    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onEvent).toHaveBeenLastCalledWith(events[1]);
    stream.stop();
  });

  it("loops the scripted events when exhausted", () => {
    const onEvent = vi.fn();
    const stream = createMockEventStream({
      events,
      intervalMs: 100,
      onEvent,
      loop: true,
    });
    stream.start();

    vi.advanceTimersByTime(400);
    expect(onEvent).toHaveBeenCalledTimes(4);
    expect(onEvent).toHaveBeenLastCalledWith(events[0]);
    stream.stop();
  });

  it("stops emitting after stop", () => {
    const onEvent = vi.fn();
    const stream = createMockEventStream({ events, intervalMs: 100, onEvent });
    stream.start();
    stream.stop();

    vi.advanceTimersByTime(1000);
    expect(onEvent).not.toHaveBeenCalled();
  });
});
