/* Live page contract (odd/tasks/console-live.md T2/S2): real SSE feed from
   GET /api/events/stream with pause/resume and filters; meta panels from
   GET /api/live. EventSource is stubbed with a controllable fake. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveActivityPage } from "./LiveActivityPage";
import { liveFeedFixture } from "../../mocks/fixtures";
import type { StreamEnvelope } from "../../api/useLiveEvents";

const server = setupServer(
  http.get("*/api/live", () => HttpResponse.json(liveFeedFixture)),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readyState = 0;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  private listeners = new Map<string, ((event: { data?: string }) => void)[]>();

  constructor(public url: string) {
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

  emit(envelope: StreamEnvelope) {
    const event = { data: JSON.stringify(envelope) };
    const named = this.listeners.get(envelope.type) ?? [];
    if (named.length > 0) {
      for (const handler of named) handler(event);
    } else {
      this.onmessage?.(event as { data: string });
    }
  }
}

function envelope(overrides: Partial<StreamEnvelope>): StreamEnvelope {
  return {
    event_id: "00000000-0000-4000-8000-000000000000",
    type: "state.transition",
    occurred_at: "2026-10-22T09:05:54.771188+00:00",
    candidate_id: null,
    trace_id: "tr_1",
    payload: {},
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LiveActivityPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function emitEvent(source: FakeEventSource, env: StreamEnvelope) {
  act(() => source.emit(env));
}

function currentSource(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("no EventSource opened");
  source.readyState = 1;
  source.onopen?.();
  return source;
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LiveActivityPage", () => {
  it("streams real SSE events into the feed, newest first", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Live agent activity" })).toBeInTheDocument();
    const source = currentSource();

    source.emit(
      envelope({
        type: "state.transition",
        event_id: "evt-2",
        payload: { actor_kind: "candidate", actor_name: "Alberto", from_state: "contacted", to_state: "consented" },
      }),
    );
    source.emit(
      envelope({
        type: "agent.turn",
        event_id: "evt-1",
        payload: { agent: "recruit", prompt_version: "v7", state: "screening", status: "ok", latency_ms: 412 },
      }),
    );

    expect(await screen.findByText(/contacted -> consented/)).toBeInTheDocument();
    expect(screen.getByText(/Recruit agent turn in screening/)).toBeInTheDocument();
    expect(screen.getByText(/Streaming - 2 events/)).toBeInTheDocument();
  });

  it("renders the health panel metrics from GET /api/live", async () => {
    renderPage();
    expect(await screen.findByText("p95 reply latency")).toBeInTheDocument();
    expect(await screen.findByText("1.8 s")).toBeInTheDocument();
    expect(screen.getByText("\u20AC8.41")).toBeInTheDocument();
  });

  it("renders the guardrails panel", async () => {
    renderPage();
    expect(await screen.findByText("Guardrails")).toBeInTheDocument();
    expect(await screen.findByText("No offer without approval")).toBeInTheDocument();
    expect(screen.getByText("1 injection attempt blocked")).toBeInTheDocument();
  });

  it("expands an agent turn row to show prompt, model, tokens and validation", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Live agent activity" });
    emitEvent(currentSource(), 
      envelope({
        type: "agent.turn",
        event_id: "evt-1",
        payload: {
          agent: "recruit",
          prompt_version: "v7",
          model: "claude-sonnet-5-5",
          state: "screening",
          status: "ok",
          latency_ms: 412,
          tokens: { input: 1842, output: 214 },
          validation_retries: 2,
        },
      }),
    );
    await user.click(await screen.findByText(/Recruit agent turn in screening/));
    expect(screen.getAllByText("recruit@v7").length).toBeGreaterThan(0);
    expect(screen.getByText("claude-sonnet-5-5")).toBeInTheDocument();
    expect(screen.getByText(/1,842 in - 214 out/)).toBeInTheDocument();
    expect(screen.getByText("2 schema re-asks")).toBeInTheDocument();
    expect(screen.getByText("View trace")).toBeInTheDocument();
  });

  it("expands a tool.call row to show the tool arguments and result JSON", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Live agent activity" });
    emitEvent(currentSource(), 
      envelope({
        type: "tool.call",
        event_id: "evt-3",
        payload: { agent: "recruit", tool: "propose_shifts", status: "ok", state: "screening", result: { candidate_id: "C-0214" } },
      }),
    );
    await user.click(await screen.findByText(/tool propose_shifts \(ok\)/));
    expect(screen.getByText(/propose_shifts - arguments and result/)).toBeInTheDocument();
    expect(screen.getByText(/"candidate_id": "C-0214"/)).toBeInTheDocument();
  });

  it("filters the feed by event kind", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Live agent activity" });
    const source = currentSource();
    source.emit(
      envelope({
        type: "agent.turn",
        event_id: "evt-1",
        payload: { agent: "recruit", prompt_version: "v7", state: "screening", status: "ok" },
      }),
    );
    source.emit(
      envelope({
        type: "integration.write",
        event_id: "evt-2",
        payload: { port: "hiredesk", operation: "interview_scheduled" },
      }),
    );
    await screen.findByText(/Recruit agent turn in screening/);

    await user.click(screen.getByRole("tab", { name: /Integrations/ }));
    expect(screen.getByText(/write hiredesk interview_scheduled/)).toBeInTheDocument();
    expect(screen.queryByText(/Recruit agent turn in screening/)).not.toBeInTheDocument();
  });

  it("pauses the feed so later events do not render, then resumes", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Live agent activity" });
    const source = currentSource();
    source.emit(
      envelope({
        type: "state.transition",
        event_id: "evt-1",
        payload: { actor_kind: "candidate", actor_name: "Alberto", to_state: "consented" },
      }),
    );
    await screen.findByText(/entered consented/);

    await user.click(screen.getByRole("button", { name: "Pause feed" }));
    expect(screen.getByRole("button", { name: "Resume feed" })).toBeInTheDocument();
    expect(screen.getByText(/Paused - 1 events/)).toBeInTheDocument();

    source.emit(
      envelope({
        type: "state.transition",
        event_id: "evt-2",
        payload: { actor_kind: "system", actor_name: "firstshift-webhook", to_state: "contacted" },
      }),
    );
    await waitFor(() => {
      expect(screen.queryByText(/entered contacted/)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Paused - 1 events/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resume feed" }));
    expect(screen.getByRole("button", { name: "Pause feed" })).toBeInTheDocument();
  });

  it("shows Reconnecting while the stream is down", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Live agent activity" });
    const source = currentSource();
    source.onerror?.();
    expect(await screen.findByText(/Reconnecting - 0 events/)).toBeInTheDocument();
  });
});
