import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { OverviewPage } from "./OverviewPage";
import { overviewFixture } from "../../mocks/fixtures";

/* The page talks to the real API client; MSW serves the fixture body at the
   documented endpoint (fixtures stay test-only). */
const server = setupServer(
  http.get("*/api/overview", () => HttpResponse.json(overviewFixture)),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <OverviewPage />
    </QueryClientProvider>,
  );
}

describe("OverviewPage", () => {
  it("loads and shows the six KPI cards with values and status chips", async () => {
    renderPage();
    expect(await screen.findByText("Time to first productive shift")).toBeInTheDocument();
    expect(screen.getByText("4.2")).toBeInTheDocument();
    expect(screen.getByText("Time to first contact")).toBeInTheDocument();
    expect(screen.getByText("Interview show rate")).toBeInTheDocument();
    expect(screen.getByText("Offer to on rota")).toBeInTheDocument();
    expect(screen.getByText("Day-1 show rate")).toBeInTheDocument();
    expect(screen.getByText("Manager time per hire")).toBeInTheDocument();

    const belowTarget = screen.getAllByText("Below target");
    expect(belowTarget).toHaveLength(1);
    expect(screen.getAllByText("On target")).toHaveLength(5);
  });

  it("shows each KPI source endpoint for the tooltip contract", async () => {
    renderPage();
    expect(await screen.findByText("GET /metrics/kpis - ttfps")).toBeInTheDocument();
    expect(screen.getByText("GET /metrics/kpis - day1_show")).toBeInTheDocument();
  });

  it("renders the hiring funnel stages with pilot and control shares and the insight", async () => {
    renderPage();
    expect(await screen.findByText("Hiring funnel")).toBeInTheDocument();
    expect(screen.getByText("Interview attended")).toBeInTheDocument();
    expect(screen.getByText("Day 1 worked")).toBeInTheDocument();
    expect(screen.getByText(/Largest gain at Contacted/)).toBeInTheDocument();
  });

  it("renders the needs attention strip with kind labels", async () => {
    renderPage();
    expect(await screen.findByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText(/Offer approval pending for C-0193/)).toBeInTheDocument();
    expect(screen.getByText("SLA BREACH")).toBeInTheDocument();
    expect(screen.getByText("HUMAN NEEDED")).toBeInTheDocument();
    expect(screen.getByText(/Nomina360 create_employee failed/)).toBeInTheDocument();
  });

  it("renders the recent activity feed with actor labels", async () => {
    renderPage();
    expect(await screen.findByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByText(/Proposed 3 open shifts to C-0214/)).toBeInTheDocument();
    expect(screen.getByText(/Approved offer for C-0189/)).toBeInTheDocument();
  });

  it("renders the shift coverage table for the next 14 days", async () => {
    renderPage();
    expect(await screen.findByText("Shift coverage, next 14 days")).toBeInTheDocument();
    expect(screen.getByText("Benidorm Playa")).toBeInTheDocument();
    expect(screen.getByText("77%")).toBeInTheDocument();
    expect(screen.getByText("Denia Marina")).toBeInTheDocument();
  });
});
