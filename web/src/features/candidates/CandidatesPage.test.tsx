/* Candidates page contract (odd/tasks/console-live.md T3/S3): a real table
   from GET /api/candidates with state chips, restaurant, cohort, language,
   last activity and SLA risk, each row linking to the candidate journey;
   plus empty and error states. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { CandidatesPage } from "./CandidatesPage";

const candidateRow = {
  id: "bb4ca6a2-af48-4b09-987f-3a1bec6c1112",
  firstName: "Alberto",
  initials: "A",
  state: "consented",
  stateLabel: "Consent granted",
  restaurant: "Lumbre Burger Sol",
  restaurantCode: "R001",
  cohort: "pilot",
  languages: ["es"],
  agentVersion: "",
  agentInControl: true,
  slaRisk: "at_risk",
  lastActivityAt: "2026-10-23T05:26:30.964670+00:00",
  matchedShiftLabel: "",
  phoneMasked: "+34 ***** 794",
  elapsedLabel: "29h 52m",
};

function listBody(items: unknown[] = [candidateRow]) {
  return { items, total: items.length, page: 1, pageSize: 25 };
}

const server = setupServer(
  http.get("*/api/candidates", () => HttpResponse.json(listBody())),
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
      <MemoryRouter>
        <CandidatesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CandidatesPage", () => {
  it("renders a row per candidate with state, restaurant, cohort, language, last activity and SLA risk", async () => {
    renderPage();

    expect(await screen.findByRole("link", { name: /Alberto/ })).toHaveAttribute(
      "href",
      "/candidates/bb4ca6a2-af48-4b09-987f-3a1bec6c1112",
    );
    expect(screen.getAllByText("Consent granted").length).toBeGreaterThan(0);
    expect(screen.getByText("Lumbre Burger Sol")).toBeInTheDocument();
    expect(screen.getAllByText("pilot").length).toBeGreaterThan(0);
    expect(screen.getByText("es")).toBeInTheDocument();
    expect(screen.getByText("2026-10-23 05:26 UTC")).toBeInTheDocument();
    expect(screen.getByText(/At risk/)).toBeInTheDocument();
    expect(screen.getByText("+34 ***** 794")).toBeInTheDocument();
  });

  it("shows an empty state when there are no candidates", async () => {
    server.use(http.get("*/api/candidates", () => HttpResponse.json(listBody([]))));
    renderPage();

    expect(await screen.findByText(/No candidates yet/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows an error state with a retry when the API fails", async () => {
    server.use(
      http.get("*/api/candidates", () =>
        HttpResponse.json({ detail: "candidates query failed" }, { status: 500 }),
      ),
    );
    renderPage();

    expect(await screen.findByText(/candidates query failed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();

    server.use(http.get("*/api/candidates", () => HttpResponse.json(listBody())));
    await userEvent.click(screen.getByRole("button", { name: /Retry/ }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /Alberto/ })).toBeInTheDocument(),
    );
  });
});
