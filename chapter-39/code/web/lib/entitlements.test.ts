import { canUse, nextPlan, remainingMessages, type Feature, type Plan } from "./entitlements";

describe("canUse", () => {
  it.each([
    ["free", "chat", true], ["free", "image_upload", false], ["free", "export", false], ["free", "team_workspace", false],
    ["pro", "chat", true], ["pro", "image_upload", true], ["pro", "export", true], ["pro", "team_workspace", false],
    ["team", "team_workspace", true], ["team", "export", true],
  ])("%s plan, %s feature: %p", (plan: Plan, feature: Feature, expected: boolean) => {
    expect(canUse(plan, feature)).toBe(expected);
  });

  it("every higher plan keeps everything the lower plan had", () => {
    const features: Feature[] = ["chat", "image_upload", "export", "team_workspace"];
    const order: Plan[] = ["free", "pro", "team"];
    for (let i = 1; i < order.length; i += 1) {
      for (const f of features) {
        if (canUse(order[i - 1], f)) expect(canUse(order[i], f)).toBe(true);
      }
    }
  });
});

describe("remainingMessages", () => {
  it("counts down and stops at zero", () => {
    expect(remainingMessages("free", 0)).toBe(20);
    expect(remainingMessages("free", 19)).toBe(1);
    expect(remainingMessages("free", 20)).toBe(0);
    expect(remainingMessages("free", 500)).toBe(0);
  });

  it("rejects nonsense usage", () => {
    expect(() => remainingMessages("pro", -1)).toThrow();
    expect(() => remainingMessages("pro", 1.5)).toThrow();
  });
});

describe("nextPlan", () => {
  it("walks up the ladder and stops", () => {
    expect(nextPlan("free")).toBe("pro");
    expect(nextPlan("pro")).toBe("team");
    expect(nextPlan("team")).toBeNull();
  });
});
