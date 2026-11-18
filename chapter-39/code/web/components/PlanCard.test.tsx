import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PlanCard } from "./PlanCard";

const base = { name: "Pro", priceMinor: 1999, currency: "USD", features: ["Image uploads", "Export"], onChoose: () => {} };

describe("PlanCard", () => {
  it("shows the plan, its price and its features", () => {
    render(<PlanCard {...base} />);
    expect(screen.getByRole("heading", { name: "Pro" })).toBeInTheDocument();
    expect(screen.getByText("$19.99 per month")).toBeInTheDocument();
    expect(screen.getByText("Image uploads")).toBeInTheDocument();
  });

  it("tells the parent which plan was chosen when the button is clicked", async () => {
    const onChoose = jest.fn();
    render(<PlanCard {...base} onChoose={onChoose} />);
    await userEvent.click(screen.getByRole("button", { name: "Choose Pro" }));   // find it as a user would: by role and name
    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith("pro");
  });

  it("cannot be clicked twice while redirecting", async () => {
    const onChoose = jest.fn();
    render(<PlanCard {...base} loading onChoose={onChoose} />);
    const button = screen.getByRole("button", { name: "Redirecting…" });
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(onChoose).not.toHaveBeenCalled();
  });
});
