import { expect, test } from "@playwright/test";

// Synthetic seed accounts only — see apps/api/app/seed.py.
const ADMIN = { email: "admin@pa.dev", password: "Passw0rd!dev" };

test.describe("auth flow", () => {
  test("bad credentials show an error, not a session", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill("wrong-password!");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText(/Invalid credentials|401/i);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("login renders user and org list; logout returns to form", async ({ page }) => {
    const meResp = page.waitForResponse((r) => r.url().includes("/api/v1/auth/me") && r.ok());
    const orgResp = page.waitForResponse((r) => r.url().includes("/api/v1/orgs") && r.ok());
    await page.goto("/");
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await meResp; await orgResp;

    await expect(page.getByText("PA Admin")).toBeVisible();
    await expect(page.getByText("Smile Ortho (synthetic)")).toBeVisible();
    await expect(page.getByText("practice_admin")).toBeVisible();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    // session cookie revoked server-side: a fresh me() would 401
    const me = await page.request.get("/api/v1/auth/me");
    expect(me.status()).toBe(401);
  });
});
