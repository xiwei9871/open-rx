/* UAT-AUTH-01..04 — authentication & session journeys. */
import { expect, test } from "@playwright/test";
import { PA_ADMIN, PA_DOCTOR, signIn, signOut } from "./helpers";
import { totp } from "../totp";

const TOTP_SEED_SECRET = "JBSWY3DPEHPK3PXP";

test.describe("UAT-AUTH", () => {
  test("UAT-AUTH-01 login lands on home, cookies set, me() identity", async ({ page, context }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await expect(page.getByRole("heading", { name: "Patients" }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText("PA Admin")).toBeVisible({ timeout: 15000 });

    const cookies = await context.cookies();
    const sess = cookies.find((c) => c.name === "easyrs_session");
    const hint = cookies.find((c) => c.name === "easyrs_session_hint");
    expect(sess?.httpOnly, "session cookie HttpOnly").toBe(true);
    expect(sess?.sameSite, "session cookie SameSite").toMatch(/lax/i);
    expect(hint, "hint cookie present").toBeTruthy();
    expect(hint!.httpOnly, "hint must be JS-readable").toBe(false);

    const me = await page.request.get("/api/v1/auth/me");
    expect(me.ok()).toBeTruthy();
    const body = await me.json();
    expect(body.email).toBe(PA_ADMIN.email);
    expect(body.org_kind).toBe("practice");
    expect(body.role).toBe("practice_admin");
  });

  test("UAT-AUTH-02 logout clears both cookies; no revive; deep-link denied",
       async ({ page, context }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await expect(page.getByRole("heading", { name: "Patients" }))
      .toBeVisible({ timeout: 15000 });
    await signOut(page);

    const names = (await context.cookies()).map((c) => c.name);
    expect(names).not.toContain("easyrs_session");
    expect(names).not.toContain("easyrs_session_hint");

    await page.goto("/patients");
    await expect(page.getByRole("button", { name: "Sign in" }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByLabel("First name")).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("button", { name: "Sign in" }))
      .toBeVisible({ timeout: 15000 });
  });

  test("UAT-AUTH-03 refresh keeps patient + rx-detail context", async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.locator("tbody tr").first().click();
    await expect(page.getByRole("heading", { name: /,/ })).toBeVisible({ timeout: 15000 });
    await page.reload();
    await expect(page.getByRole("heading", { name: "Treatment cases" }))
      .toBeVisible({ timeout: 10000 });

    await page.getByRole("button", { name: "Prescriptions" }).click();
    const row = page.locator("tbody tr").first();
    if (await row.count()) {
      await row.click();
      const heading = await page.locator("h2").first().innerText();
      await page.reload();
      await expect(page.locator("h2").first())
        .toHaveText(heading, { timeout: 10000 });
    }
  });

  test("UAT-AUTH-04 2FA challenge rejects wrong code, accepts right code",
       async ({ page }) => {
    // mfa@pa.dev is pre-enrolled in the seed (fixed synthetic TOTP secret),
    // so the challenge flow is idempotent across reruns and parallel workers.
    await page.goto("/");
    await page.getByLabel("Email").fill("mfa@pa.dev");
    await page.getByLabel("Password").fill(PA_ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByLabel("Authentication code")).toBeVisible({ timeout: 15000 });
    await page.getByLabel("Authentication code").fill("000000");
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 15000 });
    await page.getByLabel("Authentication code").fill(totp(TOTP_SEED_SECRET));
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByText("MFA Doc")).toBeVisible({ timeout: 15000 });
  });
});
