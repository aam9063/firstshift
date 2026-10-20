import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

function renderShell() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AppShell>view under test</AppShell>
    </MemoryRouter>,
  );
}

describe("AppShell", () => {
  it("shows the simulation banner with the pilot day and the synthetic data note", () => {
    renderShell();
    expect(screen.getByText(/Day 18 of 90/)).toBeInTheDocument();
    expect(
      screen.getByText("All candidates, restaurants and numbers are synthetic"),
    ).toBeInTheDocument();
  });

  it("lists the three agents with their prompt versions in the sidebar", () => {
    renderShell();
    expect(screen.getByText("recruit@v7")).toBeInTheDocument();
    expect(screen.getByText("onboard@v4")).toBeInTheDocument();
    expect(screen.getByText("pulse@v2")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Pause all agents" }),
    ).toBeInTheDocument();
  });

  it("navigates to the live view from the sidebar", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole("link", { name: /Live activity/ }));
    expect(screen.getByRole("link", { name: /Live activity/ })).toHaveAttribute(
      "href",
      "/live",
    );
  });

  it("switches the acting role from the header picker", async () => {
    const user = userEvent.setup();
    renderShell();
    expect(screen.getByText("Viewing as Talent team")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Viewing as/ }));
    await user.click(screen.getByRole("button", { name: "Ops" }));
    expect(screen.getByText("Viewing as Ops")).toBeInTheDocument();
  });
});
