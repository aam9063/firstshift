import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { CandidateJourneyPage } from "./CandidateJourneyPage";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/candidates/C-0214"]}>
        <Routes>
          <Route path="/candidates/:id" element={<CandidateJourneyPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CandidateJourneyPage", () => {
  it("loads the candidate header with state, restaurant, languages and agent in control", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Ines Carvalho" })).toBeInTheDocument();
    expect(screen.getAllByText("Interview booked").length).toBeGreaterThan(0);
    expect(screen.getByText("Benidorm Playa")).toBeInTheDocument();
    expect(screen.getByText("Recruit agent in control")).toBeInTheDocument();
    expect(screen.getByText(/\+351 \*\*\*\*\* \*412/)).toBeInTheDocument();
  });

  it("renders the journey timeline with the current state highlighted", async () => {
    renderPage();
    expect((await screen.findAllByText("Consent")).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Interview booked").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Applied via QR poster/)).toBeInTheDocument();
  });

  it("renders the candidate thread with agent tags and tool call markers", async () => {
    renderPage();
    expect(await screen.findByText(/Sou a assistente virtual/)).toBeInTheDocument();
    expect(screen.getByText(/Ainda procuram pessoas\?/)).toBeInTheDocument();
    expect(screen.getAllByText(/recruit@v7/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/get_open_shifts/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/propose_shifts/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/request_manager_decision/).length).toBeGreaterThan(0);
  });

  it("switches to the manager thread", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Sou a assistente virtual/);
    await user.click(screen.getByRole("tab", { name: /Manager thread/ }));
    expect(screen.getByText(/matched 3 of 22 open shifts/)).toBeInTheDocument();
    expect(screen.getByText("Confirmo sabado 11:00")).toBeInTheDocument();
  });

  it("renders the record rail with matched shift, summary, consent and writes", async () => {
    renderPage();
    expect(await screen.findByText("Matched shift")).toBeInTheDocument();
    expect(screen.getByText(/Fri and Sat/)).toBeInTheDocument();
    expect(screen.getByText("Right to work")).toBeInTheDocument();
    expect(screen.getByText("notice v2 - pt - 21:39:38")).toBeInTheDocument();
    expect(screen.getByText("Food hygiene module")).toBeInTheDocument();
    expect(screen.getAllByText("201").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("HireDesk")).toBeInTheDocument();
  });

  it("lets a human take over and release back to the agent", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/Sou a assistente virtual/);
    await user.click(screen.getByRole("button", { name: "Take over" }));
    expect(screen.getByText("You are in control")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Release to agent" }),
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Type your message/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Release to agent" }));
    expect(screen.getByText("Recruit agent in control")).toBeInTheDocument();
  });
});
