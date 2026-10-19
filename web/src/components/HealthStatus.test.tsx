/**
 * HealthStatus component contract: shows the backend /health status.
 * This is the first page of the console; the API contract stays the single source of truth.
 */

import type { ReactElement } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { HealthStatus } from "./HealthStatus";

const server = setupServer(
  http.get("*/health", () =>
    HttpResponse.json({ status: "ok", service: "firstshift-backend" }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe("HealthStatus", () => {
  it("renders the ok status reported by the backend", async () => {
    renderWithProviders(<HealthStatus />);

    const badge = screen.getByTestId("health-status");
    await waitFor(() => expect(badge).toHaveTextContent("ok"));
  });

  it("renders unavailable when the backend does not answer", async () => {
    server.use(http.get("*/health", () => HttpResponse.error()));
    renderWithProviders(<HealthStatus />);

    const badge = screen.getByTestId("health-status");
    await waitFor(() => expect(badge).toHaveTextContent("unavailable"));
  });
});
