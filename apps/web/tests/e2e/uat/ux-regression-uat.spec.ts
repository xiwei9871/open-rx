/* UAT-E — usability checks that can be asserted mechanically:
 * next-action affordances, field hints, error surfacing, narrow viewport. */
import { expect, test } from "@playwright/test";
import { LA_TECH, PA_ADMIN, signIn } from "./helpers";
import { ensureDataset } from "./dataset";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

test.describe("UAT-E UX mechanics", () => {
  test("UAT-E-01 primary flows reachable without documentation", async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    // every main page has an obvious next action
    await expect(page.getByRole("button", { name: "Patients" }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: "Prescriptions" }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: "Inbox" })).toBeVisible({ timeout: 15000 });
    // patient detail exposes its next actions (case, file, rx)
    await page.locator("tbody tr").first().click();
    await expect(page.getByLabel("Case label")).toBeVisible({ timeout: 15000 });
    await expect(page.getByLabel("STL file")).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button",
      { name: "New Rx for this patient" })).toBeVisible({ timeout: 15000 });
  });

  test("UAT-E-02 rx create form carries field labels for every control",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("button", { name: "New Rx" }).click();
    for (const label of ["Laboratory", "Doctor", "Location",
                         "Due date", "Notes", "Catalog item", "Arch"]) {
      await expect(page.getByLabel(label)).toBeVisible({ timeout: 15000 });
    }
    // "Patient" also matches the nested filter input — assert the select itself
    await expect(page.locator("select[name=patient]")).toBeVisible();
    // empty submit shows an understandable error, not silent
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("alert")).toContainText(/patient/i);
  });

  test("UAT-E-03 rx detail groups content into labelled sections",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    const row = page.locator("tbody tr", { hasText: /RX\d+/ }).first();
    if (await row.count()) {
      await row.locator("td").first().click();
    } else {
      // no Rx yet — make one so the detail check still runs
      await page.getByRole("button", { name: "New Rx" }).click();
      await page.locator("[name=patient_filter]").fill("Keeley");
      const sel = page.locator("select[name=patient]");
      const v = await sel.locator("option", { hasText: /Keeley/ })
        .first().getAttribute("value");
      await sel.selectOption(v!);
      await page.getByRole("button", { name: "Save draft" }).click();
    }
    for (const h of ["Items", "Attachments", "Comments"]) {
      await expect(page.getByRole("heading", { name: h })).toBeVisible({ timeout: 15000 });
    }
  });

  test("UAT-E-04 lab inbox is understandable: rx number, patient, status",
       async ({ page }) => {
    await signIn(page, LA_TECH.email, LA_TECH.password);
    await expect(page.getByRole("heading",
      { name: "Received Prescriptions" })).toBeVisible({ timeout: 15000 });
    // columns communicate identity, not raw ids
    const headers = await page.locator("thead").innerText();
    expect(headers).toMatch(/RX #|Status/i);
    expect(headers).toMatch(/Patient/i);
  });

  test("UAT-E-05 mobile 390px: nav usable, no horizontal overflow",
       async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await expect(page.getByRole("button", { name: "Patients" }))
      .toBeVisible({ timeout: 15000 });
    const over = await page.evaluate(
      () => document.documentElement.scrollWidth -
            document.documentElement.clientWidth);
    expect(over, `${over}px horizontal overflow at 390px`)
      .toBeLessThanOrEqual(1);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    const over2 = await page.evaluate(
      () => document.documentElement.scrollWidth -
            document.documentElement.clientWidth);
    expect(over2).toBeLessThanOrEqual(1);
  });
});
