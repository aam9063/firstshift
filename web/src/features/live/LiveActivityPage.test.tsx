import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { LiveActivityPage } from "./LiveActivityPage";
import { liveEventsFixture } from "../../mocks/fixtures";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    fetchLiveEventsSeed: async () => liveEventsFixture,
  };
});

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

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("LiveActivityPage", () => {
  it("shows the streaming header with the seeded event count", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Live agent activity" })).toBeInTheDocument();
    expect(await screen.findByText(/Streaming/)).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("renders the health panel metrics", async () => {
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

  it("lists the seeded events with kind labels", async () => {
    renderPage();
    expect(await screen.findByText(/Proposed 3 open shifts to C-0214/)).toBeInTheDocument();
    expect(screen.getByText(/Outbox retry 2 of 5 to Nomina360/)).toBeInTheDocument();
    expect(screen.getAllByText("tool.call").length).toBeGreaterThan(0);
  });

  it("expands a tool.call row to show model, tokens, validation and tool JSON", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByText(/Proposed 3 open shifts to C-0214/));
    expect(screen.getByText("recruit@v7")).toBeInTheDocument();
    expect(screen.getByText("claude-sonnet-5-5")).toBeInTheDocument();
    expect(screen.getByText(/ShiftProposal/)).toBeInTheDocument();
    expect(screen.getByText(/propose_shifts - arguments and result/)).toBeInTheDocument();
    expect(screen.getByText(/"candidate_id": "C-0214"/)).toBeInTheDocument();
    expect(screen.getByText("View trace")).toBeInTheDocument();
  });

  it("filters the feed by event kind", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Proposed 3 open shifts to C-0214/);
    await user.click(await screen.findByRole("tab", { name: /Agent turns/ }));
    expect(screen.getByText(/Declined an off-policy request/)).toBeInTheDocument();
    expect(screen.queryByText(/Outbox retry 2 of 5 to Nomina360/)).not.toBeInTheDocument();
  });

  it("pauses and resumes the feed", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Proposed 3 open shifts to C-0214/);
    const button = screen.getByRole("button", { name: "Pause feed" });
    await user.click(button);
    expect(screen.getByRole("button", { name: "Resume feed" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume feed" }));
    expect(screen.getByRole("button", { name: "Pause feed" })).toBeInTheDocument();
  });
});
