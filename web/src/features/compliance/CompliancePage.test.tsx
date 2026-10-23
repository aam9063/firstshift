/* Compliance contract (odd/tasks/console-views.md T4/S4): DPO role notice,
   audit log search with filters, consent records grouped by notice version
   (derived from consent audit events when the backend exposes them), erasure
   request submission with X-Actor-Role: dpo, and honest empty states for the
   data the backend does not expose yet (retention countdowns, erasure list). */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { CompliancePage } from "./CompliancePage";

const auditRow = {
  id: "ev-1",
  at: "2026-10-22T09:22:07+00:00",
  actorType: "candidate",
  actorLabel: "Alberto",
  eventType: "candidate_consents",
  stateFrom: "contacted",
  stateTo: "consented",
  summary: "candidate_consents, contacted to consent granted",
  payload: {
    channel: "whatsapp",
    folded_events: [
      { type: "consent.recorded", payload: { channel: "whatsapp", notice_version: "v1" } },
    ],
  },
};

const genericRow = {
  ...auditRow,
  id: "ev-2",
  eventType: "intake_processed",
  summary: "intake_processed, applied to contacted",
  payload: { details: "" },
};

let auditUrl = "";
const server = setupServer(
  http.get("*/api/audit", ({ request }) => {
    auditUrl = new URL(request.url).search;
    const eventType = new URL(request.url).searchParams.get("eventType");
    if (eventType === "candidate_consents") {
      return HttpResponse.json({ items: [auditRow], total: 1, limit: 200, offset: 0 });
    }
    return HttpResponse.json({ items: [auditRow, genericRow], total: 2, limit: 50, offset: 0 });
  }),
  http.post("*/api/erasure-requests", ({ request }) => {
    expect(request.headers.get("X-Actor-Role")).toBe("dpo");
    return HttpResponse.json({
      id: "er-1",
      candidateId: "c-1",
      status: "recorded",
      requestedAt: "2026-10-23T10:00:00+00:00",
    });
  }),
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
      <CompliancePage />
    </QueryClientProvider>,
  );
}

describe("CompliancePage", () => {
  it("shows the DPO role notice", async () => {
    renderPage();

    expect(await screen.findByText(/X-Actor-Role: dpo/)).toBeInTheDocument();
  });

  it("searches the audit log and renders rows", async () => {
    renderPage();

    expect(await screen.findByText(/intake_processed/)).toBeInTheDocument();
    expect(screen.getByText(/candidate_consents, contacted to consent granted/)).toBeInTheDocument();
  });

  it("passes the search query to GET /api/audit", async () => {
    renderPage();

    await screen.findByText(/intake_processed/);
    await userEvent.type(screen.getByLabelText(/Search audit log/), "consent");
    await userEvent.click(screen.getByRole("button", { name: /Search/ }));

    await waitFor(() => expect(auditUrl).toContain("q=consent"));
  });

  it("groups consent records by notice version", async () => {
    renderPage();

    expect(
      await screen.findByText(/1 consent records? at notice version v1/),
    ).toBeInTheDocument();
  });

  it("submits an erasure request with X-Actor-Role: dpo and shows the status", async () => {
    renderPage();

    await userEvent.type(
      screen.getByLabelText(/Candidate ID/),
      "bb4ca6a2-af48-4b09-987f-3a1bec6c1112",
    );
    await userEvent.type(screen.getByLabelText(/Reason/), "GDPR art. 17 request");
    await userEvent.click(screen.getByRole("button", { name: /Submit erasure request/ }));

    expect(await screen.findByText(/Erasure request recorded/)).toBeInTheDocument();
    expect(screen.getByText(/er-1 · candidate c-1/)).toBeInTheDocument();
  });

  it("renders an honest empty state for retention countdowns (no endpoint yet)", async () => {
    renderPage();

    expect(
      await screen.findByText(/not exposed by the API yet/),
    ).toBeInTheDocument();
  });
});
