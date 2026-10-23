/* Restaurants grid contract (odd/tasks/console-views.md T1/S1): one card per
   restaurant with cohort, coverage, bench, open candidates and manager reply
   median, each number carrying its source tooltip; empty and error states. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { RestaurantsPage } from "./RestaurantsPage";

const restaurant = {
  id: "r-1",
  code: "R001",
  name: "Lumbre Burger Sol",
  city: "Madrid",
  cohort: "pilot",
  openShifts: 30,
  coveredPct: 40,
  bench: 2,
  openCandidates: 3,
  managerMedianReply: "3h 10m",
  paused: false,
};

const pausedControl = {
  ...restaurant,
  id: "r-14",
  code: "R014",
  name: "Lumbre Burger Centro",
  cohort: "control",
  coveredPct: 0,
  bench: 0,
  openCandidates: 0,
  managerMedianReply: "",
  paused: true,
};

const server = setupServer(
  http.get("*/api/restaurants", () => HttpResponse.json([restaurant, pausedControl])),
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
        <RestaurantsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RestaurantsPage", () => {
  it("renders one card per restaurant linking to its detail view", async () => {
    renderPage();

    const link = await screen.findByRole("link", { name: /Lumbre Burger Sol/ });
    expect(link).toHaveAttribute("href", "/restaurants/r-1");
    expect(screen.getByText(/R001/)).toBeInTheDocument();
    expect(screen.getAllByText(/Madrid/).length).toBeGreaterThan(0);
  });

  it("shows coverage, bench, open candidates and manager median per card", async () => {
    renderPage();

    expect(await screen.findByText("40%")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.getAllByText(/^Bench/).length).toBeGreaterThan(0);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("3h 10m")).toBeInTheDocument();
  });

  it("marks an empty manager median honestly instead of inventing one", async () => {
    renderPage();

    expect(await screen.findByText("No manager decisions recorded")).toBeInTheDocument();
  });

  it("shows the cohort and a paused badge for a paused restaurant", async () => {
    renderPage();

    const cohortChips = await screen.findAllByText("control");
    expect(cohortChips.length).toBeGreaterThan(0);
    expect(screen.getByText(/Paused/)).toBeInTheDocument();
  });

  it("documents the metric sources in tooltips", async () => {
    renderPage();

    const coverage = (await screen.findAllByTitle(/GET \/api\/restaurants/))[0];
    expect(coverage.getAttribute("title")).toContain("coveredPct");
  });

  it("shows an error state with a retry when the API fails", async () => {
    server.use(
      http.get("*/api/restaurants", () =>
        HttpResponse.json({ detail: "restaurants query failed" }, { status: 500 }),
      ),
    );
    renderPage();

    expect(await screen.findByText(/restaurants query failed/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no restaurants", async () => {
    server.use(http.get("*/api/restaurants", () => HttpResponse.json([])));
    renderPage();

    expect(await screen.findByText(/No restaurants yet/)).toBeInTheDocument();
  });
});
