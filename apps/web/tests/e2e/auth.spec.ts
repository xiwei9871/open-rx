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

  test("logout clears session + hint cookies; deep link denied; no revive", async ({ page, context }) => {
    await page.goto("/");
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("PA Admin")).toBeVisible();

    // after login: session cookie (HttpOnly) + readable hint marker
    const both = await context.cookies();
    const sess = both.find((c) => c.name === "easyrs_session");
    const hint = both.find((c) => c.name === "easyrs_session_hint");
    expect(sess, "session cookie missing").toBeTruthy();
    expect(sess!.httpOnly).toBe(true);
    expect(hint, "session hint cookie missing").toBeTruthy();
    expect(hint!.httpOnly).toBe(false);

    // sign out -> the 204 response must carry delete Set-Cookie headers
    // for BOTH cookies; the jar must actually be empty afterwards.
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    const after = await context.cookies();
    expect(after.find((c) => c.name === "easyrs_session")).toBeFalsy();
    expect(after.find((c) => c.name === "easyrs_session_hint")).toBeFalsy();

    // protected deep link is denied — shows login, leaks no patient data
    await page.goto("/patients");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await expect(page.getByLabel("First name")).toHaveCount(0);
    // refresh does not revive the revoked session
    await page.reload();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("legacy session without hint cookie degrades to plain login", async ({ page, context }) => {
    // pre-upgrade browsers hold easyrs_session but no easyrs_session_hint.
    // Expected behaviour: the app simply shows the login form (no crash
    // loop, no stuck spinner); signing in again works normally.
    await page.goto("/");
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("PA Admin")).toBeVisible();
    await context.clearCookies({ name: "easyrs_session_hint" });

    await page.reload();
    await expect(page.getByRole("button", { name: "Sign in" }))
      .toBeVisible({ timeout: 10000 });
    await expect(page.getByText("PA Admin")).toHaveCount(0);

    // re-login works — no error loop
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("PA Admin")).toBeVisible();
  });
});
