import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { plans } from "@/lib/plans";
import { PricingTable } from "./PricingTable";

describe("PricingTable", () => {
  it("renders one card per plan, with the popular one marked", () => {
    render(<PricingTable plans={plans} />);
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getAllByText("Most popular")).toHaveLength(1);
    const pro = screen
      .getByRole("heading", { name: "Pro" })
      .closest("article")!;
    expect(within(pro).getByText("Most popular")).toBeInTheDocument();
  });

  it("shows monthly prices first, and free plans have no interval", () => {
    render(<PricingTable plans={plans} />);
    expect(screen.getByText("$19.00")).toBeInTheDocument();
    expect(screen.getAllByText(/\/ month/)).toHaveLength(2);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("switches every card to yearly prices when the box is ticked", async () => {
    const user = userEvent.setup();
    render(<PricingTable plans={plans} />);
    await user.click(screen.getByRole("checkbox", { name: /bill yearly/i }));
    expect(screen.getByText("$190.00")).toBeInTheDocument();
    expect(screen.getByText("$490.00")).toBeInTheDocument();
    expect(screen.getAllByText(/\/ year/)).toHaveLength(2);
  });
});
