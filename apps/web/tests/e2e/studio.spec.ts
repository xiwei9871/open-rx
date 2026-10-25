import { expect, test, type Page } from "@playwright/test";

const ADMIN = { email: "admin@pa.dev", password: "Passw0rd!dev" };

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
}

test.describe("M1 studio", () => {
  test("org settings: profile defaults, locations, roster, connections, password", async ({ page }) => {
    await signIn(page, ADMIN.email, ADMIN.password);
    await page.getByRole("button", { name: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();
    await expect(page.getByText("Profile & defaults")).toBeVisible();
    await expect(page.getByLabel("Timezone")).toHaveValue("UTC");
    // roster: add a doctor (unique names — dev DB accumulates across runs)
    const suffix = `${Date.now() % 100000}`;
    await page.getByLabel("Roster name").fill(`Dr Studio ${suffix}`);
    await page.getByRole("button", { name: "Add roster member" }).click();
    await expect(page.getByText(`Dr Studio ${suffix} (doctor)`)).toBeVisible();
    // locations
    await page.getByLabel("New location").fill(`Studio Front Desk ${suffix}`);
    await page.getByRole("button", { name: "Add location" }).click();
    await expect(page.getByRole("listitem")
      .filter({ hasText: `Studio Front Desk ${suffix}` })).toBeVisible();
  });

  test("rx create: template save/apply + tooth marking", async ({ page }) => {
    test.setTimeout(60000);
    await signIn(page, ADMIN.email, ADMIN.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("button", { name: "New Rx" }).click();

    // required selects (patient_number is sequence-generated — match by name)
    const patientOpt = page.locator("select[name=patient] option", { hasText: "Synthetic, Ava" });
    const patientValue = await patientOpt.getAttribute("value");
    await page.locator("select[name=patient]").selectOption({ value: patientValue! });
    await page.locator("select[name=lab]").selectOption({ index: 1 });
    await page.locator("select[name=catalog]").selectOption({ index: 1 });
    await page.getByRole("button", { name: "Add" }).click();

    // tooth marking — picker auto-opens for the just-added item
    await page.getByRole("button", { name: "tooth 16" }).click();
    await expect(page.getByText("16:reset")).toBeVisible();

    // save as template — inline name field, no native dialog
    let nativeDialog = false;
    page.on("dialog", (d) => { nativeDialog = true; void d.dismiss(); });
    await page.getByLabel("Template name").fill("E2E Template");
    await page.getByRole("button", { name: "Save items as template" }).click();
    await expect(
      page.getByLabel("Template", { exact: true })).toBeVisible();

    // clear items then re-apply template
    await page.getByRole("button", { name: "remove" }).click();
    await page.getByLabel("Template", { exact: true })
      .selectOption({ label: "E2E Template" });
    await expect(page.getByText(/teeth 16/)).toBeVisible();

    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByText(/draft/i).first()).toBeVisible();
    expect(nativeDialog).toBe(false);
  });
});
