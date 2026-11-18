import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChartCard } from "./dashboard/ChartCard";

const table = {
  caption: "Tokens per day",
  headers: ["Day", "Tokens"],
  rows: [
    ["Nov 2", 100],
    ["Nov 3", 250],
  ],
};

describe("ChartCard", () => {
  it("shows a loading placeholder, not a blank hole", () => {
    render(<ChartCard title="AI usage" state="loading" />);
    expect(
      screen.getByRole("status", { name: "Loading AI usage" }),
    ).toBeInTheDocument();
  });

  it("offers a retry when the request failed", async () => {
    const retry = vi.fn();
    render(<ChartCard title="AI usage" state="error" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not load");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("says plainly when there is no data", () => {
    render(<ChartCard title="AI usage" state="empty" />);
    expect(screen.getByText(/No data for this period/)).toBeInTheDocument();
  });

  it("gives screen-reader users the same numbers as a table", () => {
    render(
      <ChartCard
        title="AI usage"
        description="Tokens per day"
        state="ready"
        table={table}
      >
        <svg />
      </ChartCard>,
    );
    expect(screen.getByRole("img", { name: /AI usage/ })).toBeInTheDocument();
    const grid = screen.getByRole("table", { name: "Tokens per day" });
    expect(grid).toHaveClass("sr-only"); // invisible, but read aloud
    expect(screen.getByRole("cell", { name: "250" })).toBeInTheDocument();
  });
});
