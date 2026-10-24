/* Evals contract (odd/tasks/console-views.md T3/S3): version list, compare any
   two versions (metric deltas, deterministic checks, judge scores by
   criterion, fairness ratios under 0.8 highlighted, cost per hire) and a
   read-only replay of the worst conversations. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { EvalsPage } from "./EvalsPage";

const versions = [
  {
    version: "v1",
    label: "v1",
    generatedAt: "2026-10-22T12:26:01+00:00",
    taskSuccessRate: 1,
    costPerHireUsd: 0.002633,
  },
  {
    version: "v2",
    label: "v2",
    generatedAt: "2026-10-22T17:18:13+00:00",
    taskSuccessRate: 0.9,
    costPerHireUsd: 0.002116,
  },
];

function report(label: string, overrides: Record<string, unknown> = {}) {
  return {
    meta: { suite: "full", seed: 42, label, generated_at: "2026-10-22T12:26:01+00:00" },
    summary: {
      task_success: 44,
      task_success_rate: 1,
      deterministic_failures: 0,
      interview_show_rate: 1,
      day1_show_rate: 0.923,
      median_ttfps_hours: 152,
      total_cost_usd: 0.102684,
      cost_per_hired_usd: 0.002633,
      mean_judge_score: 2.768,
      ...overrides,
    },
    deterministic_checks: {
      failing: 0,
      checked_conversations: 44,
      per_check: {
        state_machine_invariants: { passed: 44, failed: 0 },
        tool_allow_list: { passed: 43, failed: 1 },
      },
    },
    conversations: [],
    worst_5: [
      {
        persona_id: "P001",
        label: "stops_replying/es",
        conversation_id: "eval-p001",
        trace_id: "eval-p001",
        scenario: "D1",
        final_state: "benched",
        expected_outcome: "graceful_dropout",
        task_success: true,
        task_detail: "end states ['benched']",
        judge_mean: 1.2,
        judge_scores: { clarity: 2, warmth: 1, brevity: 1, language: 1, honesty: 1 },
        transcript: [
          { role: "agent", text: "Hola Rocio: soy el asistente virtual de Lumbre Burger." },
          { role: "candidate", text: "Si, me sigue interesando." },
        ],
      },
    ],
    funnel: {},
    fairness: [
      {
        dimension: "language",
        group: "en",
        n: 11,
        selected: 10,
        rate: 0.909,
        ratio: 0.9091,
        flagged: false,
      },
      {
        dimension: "language",
        group: "mixed",
        n: 11,
        selected: 7,
        rate: 0.636,
        ratio: 0.72,
        flagged: false,
      },
    ],
    cost: {
      conversations: 44,
      turns: 210,
      total_input_tokens: 195121,
      total_output_tokens: 15397,
      total_usd: 0.102684,
      p95_latency_ms: 0.051,
      hired: 39,
      cost_per_hired_usd: 0.002633,
      per_conversation: [],
    },
    comparison: null,
    what_changed: null,
    ...overrides,
  };
}

const v1Report = report("v1");
const v2Report = report("v2", {
  summary: {
    task_success: 40,
    task_success_rate: 0.9,
    deterministic_failures: 1,
    interview_show_rate: 0.95,
    day1_show_rate: 0.9,
    median_ttfps_hours: 140,
    total_cost_usd: 0.09,
    cost_per_hired_usd: 0.002116,
    mean_judge_score: 3.1,
  },
  deterministic_checks: {
    failing: 1,
    checked_conversations: 44,
    per_check: {
      state_machine_invariants: { passed: 44, failed: 0 },
      tool_allow_list: { passed: 42, failed: 2 },
    },
  },
  fairness: [
    {
      dimension: "language",
      group: "en",
      n: 11,
      selected: 10,
      rate: 0.909,
      ratio: 0.9091,
      flagged: false,
    },
    {
      dimension: "language",
      group: "mixed",
      n: 11,
      selected: 7,
      rate: 0.636,
      ratio: 0.72,
      flagged: false,
    },
  ],
});

const server = setupServer(
  http.get("*/api/evals", () => HttpResponse.json(versions)),
  http.get("*/api/evals/v1", () => HttpResponse.json(v1Report)),
  http.get("*/api/evals/v2", () => HttpResponse.json(v2Report)),
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
      <EvalsPage />
    </QueryClientProvider>,
  );
}

describe("EvalsPage", () => {
  it("lists the eval versions with task success and cost per hire", async () => {
    renderPage();

    expect(await screen.findAllByText("v1").then((cells) => cells.length)).toBeGreaterThan(0);
    expect(screen.getAllByText("v2").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/100%/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/0\.0026/).length).toBeGreaterThan(0);
  });

  it("compares the selected two versions with metric deltas", async () => {
    renderPage();

    await screen.findAllByText("v2");
    expect(await screen.findByText(/Task success rate/)).toBeInTheDocument();
    // v2 (compare, 90%) against v1 (base, 100%): a minus 10 pt delta.
    expect(screen.getAllByText("-10 pts").length).toBeGreaterThan(0);
  });

  it("shows the deterministic checks table per version", async () => {
    renderPage();

    expect(await screen.findByText(/state_machine_invariants/)).toBeInTheDocument();
    expect(screen.getByText(/tool_allow_list/)).toBeInTheDocument();
  });

  it("shows judge scores by criterion", async () => {
    renderPage();

    expect(await screen.findByText(/clarity/)).toBeInTheDocument();
    expect(screen.getByText(/warmth/)).toBeInTheDocument();
  });

  it("highlights fairness ratios under 0.8", async () => {
    renderPage();

    expect(await screen.findByText("mixed")).toBeInTheDocument();
    const highlighted = screen.getAllByText(/Under 0\.8/);
    expect(highlighted.length).toBeGreaterThan(0);
  });

  it("shows the cost per hire with its source tooltip", async () => {
    renderPage();

    await screen.findAllByText("v2");
    const cost = (await screen.findAllByTitle(/costPerHireUsd/))[0];
    expect(cost.getAttribute("title")).toContain("GET /api/evals");
  });

  it("opens a read-only replay of a worst conversation", async () => {
    renderPage();

    await screen.findByText(/stops_replying\/es/);
    await userEvent.click(screen.getByRole("button", { name: /Replay conversation/ }));

    expect(
      await screen.findByText(/Hola Rocio: soy el asistente virtual de Lumbre Burger\./),
    ).toBeInTheDocument();
  });

  it("shows an error state when the list fails", async () => {
    server.use(
      http.get("*/api/evals", () =>
        HttpResponse.json({ detail: "eval list failed" }, { status: 500 }),
      ),
    );
    renderPage();

    expect(await screen.findByText(/eval list failed/)).toBeInTheDocument();
  });
});
