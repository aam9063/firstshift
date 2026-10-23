/* Simulator contract (odd/tasks/console-views.md T5/S5): three panes
   (candidate phone, manager phone, live timeline), scenario loader D1-D7,
   clock controls (+1 h, +1 day, next timer) and a candidate/manager message
   composer with WhatsApp-style quick replies. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { SimulatorPage } from "./SimulatorPage";

vi.mock("../../api/useLiveEvents", () => ({
  useLiveEvents: () => ({
    events: [
      {
        id: "ev-1",
        kind: "state_change",
        actorType: "system",
        actorLabel: "System",
        summary: "contacted -> consented",
        at: "16:42:00",
      },
    ],
    paused: false,
    setPaused: vi.fn(),
    connected: true,
  }),
}));

const messages = [
  {
    recipient_ref: "+34600111222",
    body: "Hola Lucia: soy el asistente virtual de Lumbre Burger.",
    quick_replies: ["Si", "No"],
    correlation_id: "c-1",
  },
  {
    recipient_ref: "+34600999888",
    body: "Yolanda, Lucia matchea con el turno de cocina del viernes.",
    quick_replies: [],
    correlation_id: "c-1",
  },
];

let clockBody: unknown = null;
let simMessageBody: unknown = null;

const server = setupServer(
  http.get("*/simulator/messages", () => HttpResponse.json(messages)),
  http.post("*/api/sim/scenarios/D1/load", ({ request }) => {
    expect(request.headers.get("content-type")).toContain("application/json");
    return HttpResponse.json({
      status: "loaded",
      scenarioId: "D1",
      state: "contacted",
      manager: { id: "mgr-yolanda-001", name: "Yolanda" },
    });
  }),
  http.post("*/api/sim/clock/advance", async ({ request }) => {
    clockBody = await request.json();
    return HttpResponse.json({
      status: "advanced",
      now: "2026-10-23T17:00:00+00:00",
      state: "consented",
      timers_fired: [{ timer: "nudge_consent" }],
      timers_skipped: [],
    });
  }),
  http.post("*/api/sim/messages", async ({ request }) => {
    simMessageBody = await request.json();
    return HttpResponse.json({
      status: "recorded",
      role: "candidate",
      event: null,
      transitioned: false,
      state: "contacted",
      trace_id: "sim-d1-1",
    });
  }),
);

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  clockBody = null;
  simMessageBody = null;
});
afterAll(() => server.close());

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SimulatorPage />
    </QueryClientProvider>,
  );
}

describe("SimulatorPage", () => {
  it("renders the candidate phone pane and the manager phone pane from the same feed", async () => {
    renderPage();

    expect(
      await screen.findByText(/Hola Lucia: soy el asistente virtual de Lumbre Burger\./),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Yolanda, Lucia matchea con el turno de cocina del viernes\./),
    ).toBeInTheDocument();
  });

  it("renders quick replies as real buttons and sends them as the candidate", async () => {
    renderPage();

    await screen.findByText(/Hola Lucia/);
    await userEvent.click(screen.getByRole("button", { name: "Si" }));

    await waitFor(() => expect(simMessageBody).not.toBeNull());
    expect(simMessageBody).toMatchObject({ role: "candidate", text: "Si" });
  });

  it("shows the live timeline from the SSE hook", async () => {
    renderPage();

    expect(await screen.findByText(/contacted -> consented/)).toBeInTheDocument();
  });

  it("loads scenario D1 through the loader", async () => {
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /D1/ }));
    await waitFor(() => expect(screen.getAllByText(/contacted/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/Yolanda/).length).toBeGreaterThan(0);
  });

  it("advances the clock one hour and jumps to the next timer", async () => {
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /\+1 h/ }));
    await waitFor(() => expect(clockBody).toEqual({ hours: 1 }));

    clockBody = null;
    await userEvent.click(screen.getByRole("button", { name: /Next timer/ }));
    await waitFor(() => expect(clockBody).toEqual({ next_timer: true }));
  });

  it("advances the clock one day", async () => {
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /\+1 day/ }));
    await waitFor(() => expect(clockBody).toEqual({ days: 1 }));
  });

  it("sends a typed message as the manager from the composer", async () => {
    renderPage();

    await screen.findByText(/Hola Lucia/);
    await userEvent.selectOptions(screen.getByLabelText(/Send as/), "manager");
    await userEvent.type(screen.getByLabelText(/Message/), "Aprobo a Lucia");
    await userEvent.click(screen.getByRole("button", { name: /Send message/ }));

    await waitFor(() => expect(simMessageBody).not.toBeNull());
    expect(simMessageBody).toMatchObject({ role: "manager", text: "Aprobo a Lucia" });
  });
});
