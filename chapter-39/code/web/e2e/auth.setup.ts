import { expect, test as setup } from "@playwright/test";

// Log in ONCE through the real form, save the browser state, and let every other test start already signed in.
setup("sign in and save the session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.E2E_EMAIL!);
  await page.getByLabel("Password").fill(process.env.E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your chats" })).toBeVisible();
  await page.context().storageState({ path: "e2e/.auth/user.json" });      // add e2e/.auth to .gitignore
});
