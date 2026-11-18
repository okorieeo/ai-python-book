import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { expectNoA11yViolations } from "@/test-utils";
import { LoginForm } from "./LoginForm";

async function fill(email: string, password: string) {
  const user = userEvent.setup();
  if (email) await user.type(screen.getByLabelText("Email"), email);
  if (password) await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

describe("LoginForm", () => {
  it("has no automatically detectable accessibility violations, empty or with errors", async () => {
    const { container } = render(<LoginForm onLogin={vi.fn()} />);
    await expectNoA11yViolations(container);
    await fill("", "");
    await screen.findByText("Enter your email address");
    await expectNoA11yViolations(container);
  });

  it("shows field errors and does not call the server for invalid input", async () => {
    const onLogin = vi.fn();
    render(<LoginForm onLogin={onLogin} />);
    await fill("not-an-email", "");
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(onLogin).not.toHaveBeenCalled();
  });

  it("submits trimmed values and calls onSuccess", async () => {
    const onLogin = vi.fn().mockResolvedValue({});
    const onSuccess = vi.fn();
    render(<LoginForm onLogin={onLogin} onSuccess={onSuccess} />);
    await fill("  ada@example.com  ", "correct horse");
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(onLogin).toHaveBeenCalledWith({ email: "ada@example.com", password: "correct horse" });
  });

  it("uses the SAME message for any 401, so it never reveals which field was wrong", async () => {
    const onLogin = vi.fn().mockRejectedValue(new ApiError({ status: 401, code: "no_such_user", message: "No account with that email" }));
    render(<LoginForm onLogin={onLogin} />);
    await fill("ghost@example.com", "whatever");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The email or password is incorrect.");
    expect(alert).not.toHaveTextContent("No account");
  });

  it("puts server field errors on the matching input", async () => {
    const onLogin = vi.fn().mockRejectedValue(new ApiError({ status: 400, code: "validation_error", message: "x", fields: { email: ["This account is disabled."] } }));
    render(<LoginForm onLogin={onLogin} />);
    await fill("ada@example.com", "pw");
    expect(await screen.findByText("This account is disabled.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("tells the user how long to wait after a 429", async () => {
    const onLogin = vi.fn().mockRejectedValue(new ApiError({ status: 429, code: "throttled", message: "x", retryAfter: 45 }));
    render(<LoginForm onLogin={onLogin} />);
    await fill("ada@example.com", "pw");
    expect(await screen.findByRole("alert")).toHaveTextContent("45 seconds");
  });

  it("disables the button while the request is in flight", async () => {
    let finish: () => void = () => {};
    const onLogin = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    render(<LoginForm onLogin={onLogin} />);
    await fill("ada@example.com", "pw");
    expect(await screen.findByRole("button", { name: /signing in/i })).toBeDisabled();
    await act(async () => finish());
  });
});
