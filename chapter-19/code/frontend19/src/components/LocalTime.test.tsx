import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LocalTime } from "./LocalTime";

const iso = "2026-11-02T09:30:00Z";

describe("LocalTime", () => {
  it("renders a stable UTC time on the server, with the zone shown", () => {
    const html = renderToString(<LocalTime iso={iso} timeZone="Asia/Tokyo" />);
    expect(html).toContain("9:30");
    expect(html).toContain("UTC");
  });

  it("shows the viewer's own time zone in the browser", () => {
    render(<LocalTime iso={iso} timeZone="Africa/Lagos" />);
    expect(screen.getByText("10:30 AM")).toBeInTheDocument(); // Lagos is UTC+1
  });

  it("uses a real <time> element with the machine-readable value", () => {
    render(<LocalTime iso={iso} timeZone="America/New_York" />);
    const element = screen.getByText("4:30 AM"); // New York is UTC-5 in November
    expect(element.tagName).toBe("TIME");
    expect(element).toHaveAttribute("dateTime", iso);
  });
});
