/* Ops queues contract (odd/tasks/console-views.md T2/S2): manager decisions
   pending with SLA countdown, first shifts unconfirmed, DLQ with replay
   (success refreshes, a 409 shows the backend message), degraded adapters,
   paused restaurants. Every action sends X-Actor-Role: ops. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { OpsPage } from "./OpsPage";

const escalations = [
  {
    id: "manager-app-1",
    kind: "sla_breach",
    title: "Manager decision pending: Lucia",
    detail: "Offer approval at Lumbre Burger Sol",
    ago: "9h 40m",
  },
  {
    id: "shift-7",
    kind: "first_shift",
    title: "First shift unconfirmed: Marco",
    detail: "Scheduled Fri 24 Oct 08:00",
    ago: "cutoff 3h",
  },
];

const outboxRow = {
  id: "ob-1",
  port: "hiredesk",
  operation: "candidate.created",
  status: "failed",
  attempts: 5,
  lastError: "502 bad gateway",
  idempotencyKey: "idem-1",
};

const adapters = {
  adapters: [
    {
      system: "hiredesk",
      status: "degraded",
      lastCheckedAt: "2026-10-23T16:44:32+00:00",
      failureReason: "probe timed out",
    },
    {
      system: "nomina360",
      status: "unknown",
      lastCheckedAt: "2026-10-23T16:44:32+00:00",
      failureReason: "adapter could not be constructed",
    },
  ],
};

const restaurants = [
  {
    id: "r-1",
    code: "R001",
    name: "Lumbre Burger Sol",
    city: "Madrid",
    cohort: "pilot",
    openShifts: 30,
    coveredPct: 0,
    bench: 0,
    openCandidates: 1,
    managerMedianReply: "",
    paused: true,
  },
];

const server = setupServer(
  http.get("*/api/escalations", () => HttpResponse.json(escalations)),
  http.get("*/api/outbox", () =>
    HttpResponse.json({ status: "failed", messages: [outboxRow] }),
  ),
  http.get("*/health/adapters", () => HttpResponse.json(adapters)),
  http.get("*/api/restaurants", () => HttpResponse.json(restaurants)),
  http.post("*/api/outbox/ob-1/replay", () =>
    HttpResponse.json({ id: "ob-1", status: "pending", attempts: 0 }),
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
      <OpsPage />
    </QueryClientProvider>,
  );
}

describe("OpsPage", () => {
  it("lists manager decisions pending with the waiting time and SLA breach badge", async () => {
    renderPage();

    expect(await screen.findByText(/Manager decision pending: Lucia/)).toBeInTheDocument();
    expect(screen.getByText("9h 40m")).toBeInTheDocument();
    expect(screen.getByText(/SLA breached/)).toBeInTheDocument();
  });

  it("lists unconfirmed first shifts in their own queue", async () => {
    renderPage();

    expect(await screen.findByText(/First shift unconfirmed: Marco/)).toBeInTheDocument();
  });

  it("shows an honest empty state for escalated conversations (no dedicated endpoint)", async () => {
    renderPage();

    expect(
      await screen.findByText(/escalated conversations queue has no dedicated endpoint yet/),
    ).toBeInTheDocument();
  });

  it("lists DLQ rows with port, operation, attempts and error", async () => {
    renderPage();

    expect(await screen.findByText(/hiredesk candidate\.created/)).toBeInTheDocument();
    expect(screen.getByText(/5 attempts/)).toBeInTheDocument();
    expect(screen.getByText(/502 bad gateway/)).toBeInTheDocument();
  });

  it("replays a DLQ row with X-Actor-Role: ops and refreshes the queue", async () => {
    let replayCalls = 0;
    server.use(
      http.post("*/api/outbox/ob-1/replay", ({ request }) => {
        replayCalls += 1;
        expect(request.headers.get("X-Actor-Role")).toBe("ops");
        return HttpResponse.json({ id: "ob-1", status: "pending", attempts: 0 });
      }),
      http.get("*/api/outbox", () =>
        HttpResponse.json({ status: "failed", messages: replayCalls === 0 ? [outboxRow] : [] }),
      ),
    );
    renderPage();

    await screen.findByText(/hiredesk candidate\.created/);
    await userEvent.click(screen.getByRole("button", { name: /Replay/ }));

    await waitFor(() =>
      expect(screen.getByText(/Dead-letter queue is empty/)).toBeInTheDocument(),
    );
  });

  it("shows the backend 409 message when a replay is rejected", async () => {
    server.use(
      http.post("*/api/outbox/ob-1/replay", () =>
        HttpResponse.json(
          {
            detail:
              "outbox message ob-1 is delivered (status: delivered): only failed rows can be replayed",
          },
          { status: 409 },
        ),
      ),
    );
    renderPage();

    await screen.findByText(/hiredesk candidate\.created/);
    await userEvent.click(screen.getByRole("button", { name: /Replay/ }));

    expect(
      await screen.findByText(/only failed rows can be replayed/),
    ).toBeInTheDocument();
  });

  it("lists degraded adapters with their failure reason", async () => {
    renderPage();

    expect(await screen.findAllByText(/hiredesk/).then((rows) => rows.length)).toBeGreaterThan(0);
    expect(screen.getAllByText(/probe timed out/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Degraded/)).toBeInTheDocument();
  });

  it("lists paused restaurants and resumes them with X-Actor-Role: ops", async () => {
    let role: string | null = null;
    let body: unknown = null;
    server.use(
      http.post("*/api/restaurants/r-1/pause", async ({ request }) => {
        role = request.headers.get("X-Actor-Role");
        body = await request.json();
        return HttpResponse.json({ restaurantId: "r-1", code: "R001", paused: false });
      }),
    );
    renderPage();

    expect(await screen.findAllByText(/Lumbre Burger Sol/).then((rows) => rows.length)).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Paused$/).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: /Resume/ }));
    await waitFor(() => expect(role).toBe("ops"));
    expect(body).toEqual({ resume: true });
  });
});
