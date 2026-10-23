/* API client contract (odd/tasks/console-live.md T1/S1): every function
   fetches its documented endpoint against VITE_API_URL and surfaces typed
   errors for non-2xx and network failures. No fixtures are involved. */

import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { ApiError, fetchCandidate, fetchCandidates, fetchLiveFeedMeta, fetchOverview } from "./client";

const server = setupServer();

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("fetchOverview", () => {
  it("GETs /api/overview and returns the parsed body", async () => {
    const body = { simClock: "2026-10-22T09:00:00+00:00", pilotDay: 1, kpis: [] };
    server.use(http.get("*/api/overview", () => HttpResponse.json(body)));

    await expect(fetchOverview()).resolves.toEqual(body);
  });

  it("throws an ApiError with status and message on a 500", async () => {
    server.use(
      http.get("*/api/overview", () =>
        HttpResponse.json({ detail: "overview query failed" }, { status: 500 }),
      ),
    );

    await expect(fetchOverview()).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      message: "overview query failed",
    });
  });

  it("falls back to the status line when the error body has no detail", async () => {
    server.use(http.get("*/api/overview", () => new HttpResponse(null, { status: 503 })));

    const error = await fetchOverview().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).message).toContain("503");
  });

  it("wraps network failures in an ApiError with status 0", async () => {
    server.use(http.get("*/api/overview", () => HttpResponse.error()));

    const error = await fetchOverview().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toContain("/api/overview");
  });
});

describe("fetchLiveFeedMeta", () => {
  it("GETs /api/live and returns health, guardrails and agents", async () => {
    const body = {
      health: { windowLabel: "last 24 h", outboxInDlq: 0 },
      guardrails: [{ id: "ai_disclosure", ok: true, label: "AI disclosure" }],
      agents: [{ id: "recruit", label: "Recruit", version: "v1" }],
    };
    server.use(http.get("*/api/live", () => HttpResponse.json(body)));

    const data = await fetchLiveFeedMeta();
    expect(data).toEqual(body);
  });
});

describe("fetchCandidates", () => {
  it("GETs /api/candidates and returns the paginated list", async () => {
    const body = {
      items: [
        {
          id: "c-1",
          firstName: "Alberto",
          state: "consented",
          stateLabel: "Consent granted",
          restaurant: "Lumbre Burger Sol",
          slaRisk: "ok",
        },
      ],
      total: 1,
      page: 1,
      pageSize: 25,
    };
    server.use(http.get("*/api/candidates", () => HttpResponse.json(body)));

    const data = await fetchCandidates();
    expect(data).toEqual(body);
    expect(data.items).toHaveLength(1);
  });
});

describe("fetchCandidate", () => {
  it("GETs /api/candidates/{id} and returns the journey detail", async () => {
    const body = { id: "c-1", firstName: "Alberto", journey: [] };
    server.use(http.get("*/api/candidates/c-1", () => HttpResponse.json(body)));

    const data = await fetchCandidate("c-1");
    expect(data).toEqual(body);
  });

  it("throws an ApiError with the backend message on 404", async () => {
    server.use(
      http.get("*/api/candidates/nope", () =>
        HttpResponse.json({ detail: "candidate not found" }, { status: 404 }),
      ),
    );

    await expect(fetchCandidate("nope")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "candidate not found",
    });
  });
});
