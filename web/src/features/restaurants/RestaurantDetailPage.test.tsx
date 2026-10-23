/* Restaurant detail contract (odd/tasks/console-views.md T1/S1): the open
   shifts list grouped by day with the matched candidate per shift, plus the
   bench. The bench list endpoint does not exist yet, so the bench renders an
   honest empty state when the backend exposes only the count. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { RestaurantDetailPage } from "./RestaurantDetailPage";

const restaurant = {
  id: "r-1",
  code: "R001",
  name: "Lumbre Burger Sol",
  city: "Madrid",
  cohort: "pilot",
  openShifts: 2,
  coveredPct: 50,
  bench: 0,
  openCandidates: 1,
  managerMedianReply: "3h 10m",
  paused: false,
};

const shifts = [
  {
    id: "R001-20261023-kitchen",
    label: "kitchen, Fri 23 Oct 08:00-16:00",
    startsAt: "2026-10-23T08:00:00+00:00",
    endsAt: "2026-10-23T16:00:00+00:00",
    role: "kitchen",
    requiresFoodHygiene: true,
    status: "open",
    matchedCandidateId: "c-1",
    matchedCandidateName: "Lucia",
  },
  {
    id: "R001-20261023-till",
    label: "till, Fri 23 Oct 14:00-21:00",
    startsAt: "2026-10-23T14:00:00+00:00",
    endsAt: "2026-10-23T21:00:00+00:00",
    role: "till",
    requiresFoodHygiene: false,
    status: "open",
    matchedCandidateId: null,
    matchedCandidateName: null,
  },
];

const server = setupServer(
  http.get("*/api/restaurants/r-1/shifts", () =>
    HttpResponse.json({ restaurant, shifts }),
  ),
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
      <MemoryRouter initialEntries={["/restaurants/r-1"]}>
        <Routes>
          <Route path="/restaurants/:id" element={<RestaurantDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RestaurantDetailPage", () => {
  it("shows the restaurant header with cohort and paused state", async () => {
    renderPage();

    expect(await screen.findByText(/Lumbre Burger Sol/)).toBeInTheDocument();
    expect(screen.getAllByText("pilot").length).toBeGreaterThan(0);
  });

  it("lists the open shifts grouped by day with role and times", async () => {
    renderPage();

    expect(await screen.findByText("kitchen, Fri 23 Oct 08:00-16:00")).toBeInTheDocument();
    expect(screen.getByText("till, Fri 23 Oct 14:00-21:00")).toBeInTheDocument();
  });

  it("shows the matched candidate per shift and keeps unmatched shifts open", async () => {
    renderPage();

    expect(await screen.findByText(/Matched: Lucia/)).toBeInTheDocument();
    expect(screen.getByText(/Unmatched/)).toBeInTheDocument();
  });

  it("flags the food hygiene requirement on the shift", async () => {
    renderPage();

    expect(await screen.findByText("kitchen, Fri 23 Oct 08:00-16:00")).toBeInTheDocument();
    expect(screen.getAllByText(/Food hygiene required/).length).toBeGreaterThan(0);
  });

  it("renders an honest bench empty state because the API exposes only the bench count", async () => {
    renderPage();

    expect(await screen.findByText(/Bench/)).toBeInTheDocument();
    expect(
      screen.getByText(/No benched candidates for this restaurant yet/),
    ).toBeInTheDocument();
  });

  it("shows an error state when the restaurant is unknown", async () => {
    server.use(
      http.get("*/api/restaurants/r-1/shifts", () =>
        HttpResponse.json({ detail: "unknown restaurant" }, { status: 404 }),
      ),
    );
    renderPage();

    expect(await screen.findByText(/unknown restaurant/)).toBeInTheDocument();
  });
});
