/* Contract tests for the console-views endpoints (odd/tasks/console-views.md
   T1-T5): restaurants, ops queues (escalations, adapters, outbox), audit,
   evals, erasure requests and the simulator. Mutating calls must carry the
   documented X-Actor-Role header, and errors surface the backend detail. */

import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  advanceSimClock,
  createErasureRequest,
  fetchAdapterHealth,
  fetchAudit,
  fetchEscalations,
  fetchEvalReport,
  fetchEvalVersions,
  fetchOutbox,
  fetchRestaurantShifts,
  fetchRestaurants,
  fetchSimulatorMessages,
  loadSimScenario,
  pauseRestaurant,
  replayOutboxMessage,
  sendSimMessage,
} from "./client";

const server = setupServer();

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("fetchRestaurants", () => {
  it("GETs /api/restaurants and returns the restaurant rows", async () => {
    const body = [
      {
        id: "r-1",
        code: "R001",
        name: "Lumbre Burger Sol",
        city: "Madrid",
        cohort: "pilot",
        openShifts: 30,
        coveredPct: 0,
        bench: 2,
        openCandidates: 1,
        managerMedianReply: "3h 10m",
        paused: false,
      },
    ];
    server.use(http.get("*/api/restaurants", () => HttpResponse.json(body)));

    await expect(fetchRestaurants()).resolves.toEqual(body);
  });
});

describe("fetchRestaurantShifts", () => {
  it("GETs /api/restaurants/{id}/shifts", async () => {
    const body = {
      restaurant: { id: "r-1", code: "R001", name: "Lumbre Burger Sol", bench: 2 },
      shifts: [
        {
          id: "R001-20261023-kitchen",
          label: "kitchen, Fri 23 Oct 08:00-16:00",
          startsAt: "2026-10-23T08:00:00+00:00",
          endsAt: "2026-10-23T16:00:00+00:00",
          role: "kitchen",
          requiresFoodHygiene: true,
          status: "open",
          matchedCandidateId: null,
          matchedCandidateName: null,
        },
      ],
    };
    server.use(http.get("*/api/restaurants/r-1/shifts", () => HttpResponse.json(body)));

    await expect(fetchRestaurantShifts("r-1")).resolves.toEqual(body);
  });
});

describe("fetchAdapterHealth", () => {
  it("GETs /health/adapters (outside the /api prefix)", async () => {
    const body = {
      adapters: [
        {
          system: "hiredesk",
          status: "degraded",
          lastCheckedAt: "2026-10-23T16:44:32+00:00",
          failureReason: "probe timed out",
        },
      ],
    };
    server.use(http.get("*/health/adapters", () => HttpResponse.json(body)));

    await expect(fetchAdapterHealth()).resolves.toEqual(body);
  });
});

describe("fetchEscalations", () => {
  it("GETs /api/escalations", async () => {
    const body = [
      {
        id: "manager-app-1",
        kind: "sla_breach",
        title: "Manager decision pending: Lucia",
        detail: "Offer approval at Lumbre Burger Sol",
        ago: "9h 40m",
      },
    ];
    server.use(http.get("*/api/escalations", () => HttpResponse.json(body)));

    await expect(fetchEscalations()).resolves.toEqual(body);
  });
});

describe("fetchOutbox", () => {
  it("GETs /api/outbox?status=failed and sends X-Actor-Role", async () => {
    let role: string | null = null;
    server.use(
      http.get("*/api/outbox", ({ request }) => {
        role = request.headers.get("X-Actor-Role");
        return HttpResponse.json({
          status: "failed",
          messages: [
            {
              id: "ob-1",
              port: "hiredesk",
              operation: "candidate.created",
              status: "failed",
              attempts: 5,
              lastError: "502 bad gateway",
              idempotencyKey: "idem-1",
            },
          ],
        });
      }),
    );

    const data = await fetchOutbox("failed", "ops");
    expect(data.messages).toHaveLength(1);
    expect(role).toBe("ops");
  });
});

describe("replayOutboxMessage", () => {
  it("POSTs to /api/outbox/{id}/replay with X-Actor-Role: ops", async () => {
    let role: string | null = null;
    server.use(
      http.post("*/api/outbox/ob-1/replay", ({ request }) => {
        role = request.headers.get("X-Actor-Role");
        return HttpResponse.json({ id: "ob-1", status: "pending", attempts: 0 });
      }),
    );

    const data = await replayOutboxMessage("ob-1");
    expect(data.status).toBe("pending");
    expect(role).toBe("ops");
  });

  it("surfaces the backend 409 detail so the view can show the conflict message", async () => {
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

    await expect(replayOutboxMessage("ob-1")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: expect.stringContaining("only failed rows can be replayed"),
    });
  });
});

describe("pauseRestaurant", () => {
  it("POSTs /api/restaurants/{id}/pause with X-Actor-Role: ops and a resume body", async () => {
    let role: string | null = null;
    let body: unknown = null;
    server.use(
      http.post("*/api/restaurants/r-1/pause", async ({ request }) => {
        role = request.headers.get("X-Actor-Role");
        body = await request.json();
        return HttpResponse.json({ restaurantId: "r-1", code: "R001", paused: true });
      }),
    );

    const data = await pauseRestaurant("r-1", { resume: false });
    expect(data.paused).toBe(true);
    expect(role).toBe("ops");
    expect(body).toEqual({ resume: false });
  });
});

describe("fetchAudit", () => {
  it("GETs /api/audit passing q and eventType filters", async () => {
    let url = "";
    server.use(
      http.get("*/api/audit", ({ request }) => {
        url = new URL(request.url).search;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      }),
    );

    await fetchAudit({ q: "consent", eventType: "candidate_consents" });
    expect(url).toContain("q=consent");
    expect(url).toContain("eventType=candidate_consents");
  });
});

describe("fetchEvalVersions and fetchEvalReport", () => {
  it("GETs /api/evals and /api/evals/{version}", async () => {
    const list = [
      {
        version: "v1",
        label: "v1",
        generatedAt: "2026-10-22T12:26:01+00:00",
        taskSuccessRate: 1,
        costPerHireUsd: 0.002633,
      },
    ];
    server.use(http.get("*/api/evals", () => HttpResponse.json(list)));

    const report = { meta: { label: "v1" }, summary: { task_success: 44 } };
    server.use(http.get("*/api/evals/v1", () => HttpResponse.json(report)));

    await expect(fetchEvalVersions()).resolves.toEqual(list);
    await expect(fetchEvalReport("v1")).resolves.toEqual(report);
  });
});

describe("createErasureRequest", () => {
  it("POSTs /api/erasure-requests with X-Actor-Role: dpo", async () => {
    let role: string | null = null;
    let body: unknown = null;
    server.use(
      http.post("*/api/erasure-requests", async ({ request }) => {
        role = request.headers.get("X-Actor-Role");
        body = await request.json();
        return HttpResponse.json({
          id: "er-1",
          candidateId: "c-1",
          status: "recorded",
          requestedAt: "2026-10-23T10:00:00+00:00",
        });
      }),
    );

    const data = await createErasureRequest({ candidateId: "c-1", reason: "GDPR art. 17" });
    expect(data.status).toBe("recorded");
    expect(role).toBe("dpo");
    expect(body).toEqual({ candidate_id: "c-1", reason: "GDPR art. 17" });
  });
});

describe("simulator client functions", () => {
  it("loads a scenario, advances the clock and sends sim messages", async () => {
    server.use(
      http.post("*/api/sim/scenarios/D1/load", () =>
        HttpResponse.json({
          status: "loaded",
          scenarioId: "D1",
          state: "contacted",
          manager: { id: "mgr-yolanda-001", name: "Yolanda" },
        }),
      ),
      http.post("*/api/sim/clock/advance", async ({ request }) => {
        const body = (await request.json()) as { hours?: number; next_timer?: boolean };
        expect(body).toEqual({ hours: 1 });
        return HttpResponse.json({
          status: "advanced",
          now: "2026-10-23T17:00:00+00:00",
          state: "consented",
          timers_fired: [],
          timers_skipped: [],
        });
      }),
      http.post("*/api/sim/messages", async ({ request }) => {
        const body = (await request.json()) as { role: string; text: string };
        expect(body.role).toBe("candidate");
        return HttpResponse.json({ status: "recorded", role: "candidate", state: "contacted" });
      }),
    );

    const loaded = await loadSimScenario("D1");
    expect(loaded.status).toBe("loaded");
    const advanced = await advanceSimClock({ hours: 1 });
    expect(advanced.state).toBe("consented");
    await expect(sendSimMessage({ role: "candidate", text: "Si" })).resolves.toMatchObject({
      status: "recorded",
    });
  });

  it("GETs /simulator/messages for the phone panes", async () => {
    server.use(
      http.get("*/simulator/messages", () =>
        HttpResponse.json([
          {
            recipient_ref: "+34600111222",
            body: "Hola Lucia",
            quick_replies: ["Si", "No"],
            correlation_id: "c-1",
          },
        ]),
      ),
    );

    await expect(fetchSimulatorMessages()).resolves.toEqual([
      {
        recipientRef: "+34600111222",
        body: "Hola Lucia",
        quickReplies: ["Si", "No"],
        correlationId: "c-1",
      },
    ]);
  });
});
