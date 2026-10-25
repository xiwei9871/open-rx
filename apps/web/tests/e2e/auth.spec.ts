import { expect, test } from "@playwright/test";
import { totp } from "./totp";

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

  test("login renders the patient workbench; logout returns to form", async ({ page }) => {
    const meResp = page.waitForResponse((r) => r.url().includes("/api/v1/auth/me") && r.ok());
    const patResp = page.waitForResponse((r) => r.url().includes("/api/v1/patients") && r.ok());
    await page.goto("/");
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await meResp; await patResp;

    await expect(page.getByText("PA Admin")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
    await expect(page.getByText("Synthetic, Ava")).toBeVisible();
    await expect(page.getByText("practice_admin")).toBeVisible();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    // session cookie revoked server-side: a fresh me() would 401
    const me = await page.request.get("/api/v1/auth/me");
    expect(me.status()).toBe(401);
  });

  test("2FA-enabled user completes the challenge in the browser", async ({ page, request }) => {
    // doctor@pa.dev — NOT the shared admin account, so enabling TOTP here
    // never contaminates the other specs' plain-login flow.
    const DOCTOR = { email: "doctor@pa.dev", password: "Passw0rd!dev" };
    const api = request;
    await api.post("/api/v1/auth/login", {
      data: { email: DOCTOR.email, password: DOCTOR.password },
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const setup = await api.post("/api/v1/auth/2fa/setup",
      { headers: { "X-Requested-With": "XMLHttpRequest" } });
    expect(setup.status()).toBe(200);
    const { secret } = await setup.json();
    const enable = await api.post("/api/v1/auth/2fa/enable", {
      data: { secret, code: totp(secret) },
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    expect(enable.status()).toBe(204);
    await api.post("/api/v1/auth/logout",
      { headers: { "X-Requested-With": "XMLHttpRequest" } });

    await page.goto("/");
    await page.getByLabel("Email").fill(DOCTOR.email);
    await page.getByLabel("Password").fill(DOCTOR.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByLabel("Authentication code")).toBeVisible();
    // wrong code first -> stays on the challenge
    await page.getByLabel("Authentication code").fill("000000");
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await page.getByLabel("Authentication code").fill(totp(secret));
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByText("Dr. Demo")).toBeVisible();
  });
});
