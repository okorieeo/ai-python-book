import { expect, test } from "@playwright/test";

// Every test starts from a known state. Tests that share state are tests that fail in the wrong order.
test.beforeEach(async ({ request }) => {
  await request.post("/__test__/reset");
});

test("the pricing page shows both plans with their prices", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: "Choose a plan" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose Pro" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Choose Team" })).toBeEnabled();
  await expect(page.getByText("$19.99 per month")).toBeVisible();
});

test("a purchase shows 'pending' until the webhook arrives, then activates", async ({ page, request }) => {
  await page.goto("/pricing");
  await page.getByRole("button", { name: "Choose Pro" }).click();

  await expect(page).toHaveURL(/\/checkout\/success/);
  await expect(page.getByRole("status")).toHaveText("Payment pending…");

  // The real provider would call our server. In a test, WE deliver that call, at the moment we choose.
  await request.post("/__test__/deliver-webhook");

  await expect(page.getByRole("status")).toHaveText("Pro plan active");
});

test("a declined card shows a clear message and stays on the pricing page", async ({ page }) => {
  await page.route("**/api/checkout", (route) =>
    route.fulfill({ status: 402, contentType: "application/json", body: JSON.stringify({ message: "Your card was declined." }) }));

  await page.goto("/pricing");
  await page.getByRole("button", { name: "Choose Pro" }).click();

  await expect(page.getByRole("alert")).toHaveText("Your card was declined.");
  await expect(page).toHaveURL(/\/pricing$/);
});

test("a dropped connection during checkout shows a retry message instead of a blank page", async ({ page }) => {
  await page.route("**/api/checkout", (route) => route.abort("failed"));

  await page.goto("/pricing");
  await page.getByRole("button", { name: "Choose Team" }).click();

  await expect(page.getByRole("alert")).toContainText("Try again");
});

test("the tests never talk to a real payment provider", async ({ page, baseURL }) => {
  const outside: string[] = [];
  page.on("request", (req) => {
    if (!req.url().startsWith(baseURL!)) outside.push(req.url());
  });

  await page.goto("/pricing");
  await page.getByRole("button", { name: "Choose Pro" }).click();
  await expect(page.getByRole("status")).toBeVisible();

  expect(outside).toEqual([]);
});
