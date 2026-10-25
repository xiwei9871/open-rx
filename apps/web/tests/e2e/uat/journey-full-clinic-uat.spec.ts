/* UAT-JOURNEY — one complete clinic journey, browser-only for the
 * asserted actions: patient -> case -> STL -> Rx -> attach -> submit ->
 * lab inbox -> download/check-in -> complete -> QC -> ship -> receive ->
 * deliver. Proves the Patient->Case->Asset->Rx->Delivery loop closes. */
import { expect, test } from "@playwright/test";
import { LA_TECH, PA_ADMIN, selectByText, signIn, signOut } from "./helpers";
import { ensureDataset } from "./dataset";
import { FIX, pwFile } from "./fixtures";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

test.describe("UAT-JOURNEY", () => {
  test("full clinic loop: P05 retainer from intake to delivery",
       async ({ page }) => {
    test.setTimeout(120000);
    // ---------- practice: patient intake ----------
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByLabel("Search").fill("UAT-P05");
    const prow = page.locator("tbody tr", { hasText: "UAT-P05" }).first();
    await expect(prow).toBeVisible({ timeout: 10000 });
    await prow.click();
    await expect(page.getByRole("heading",
      { name: /Lindqvist, Noor/ })).toBeVisible({ timeout: 15000 });

    // treatment case exists (dataset) — verify it renders
    await expect(page.getByText(/Fixed retainer — active/)).toBeVisible({ timeout: 15000 });

    // upload both jaws (dedup makes re-runs idempotent)
    for (const [f, jaw] of [[FIX.upperBasic, "upper"],
                            [FIX.lowerBasic, "lower"]] as const) {
      const already = await page.locator("li",
        { hasText: f.sha256.slice(0, 16) }).count();
      if (!already) {
        await page.getByLabel("STL file").setInputFiles(pwFile(f));
        await page.getByLabel("Jaw").selectOption(jaw);
        await page.getByRole("button", { name: "Upload STL" }).click();
        await expect(page.getByText(f.sha256.slice(0, 16)))
          .toBeVisible({ timeout: 30000 });
      }
    }

    // new Rx directly from the patient page (closed loop entry point)
    await page.getByRole("button",
      { name: "New Rx for this patient" }).click();
    await expect(page).toHaveURL(/\/rx\/new\?patient=/);
    // patient preselected; attach the treatment case
    await expect(page.getByLabel("Treatment case")).toBeVisible({ timeout: 15000 });
    await selectByText(page, "Treatment case", /Fixed retainer/);
    await selectByText(page, "Laboratory", "Friendly Lab");
    await selectByText(page, "Doctor", "Dr. Demo");
    await page.getByLabel("Due date").fill("2030-08-31");
    await page.getByLabel("Notes").fill("UAT-JOURNEY P05 fixed retainer");
    await selectByText(page, "catalog", "Hawley retainer");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });

    // attach BOTH patient STLs into the Rx from the web — option labels
    // are `stl/{jaw} {sha8}…`, so select by the kind/jaw prefix.
    for (const f of [FIX.upperBasic, FIX.lowerBasic]) {
      await selectByText(page, "Patient file",
        new RegExp(`stl/${f === FIX.upperBasic ? "upper" : "lower"} `));
      await page.getByRole("button", { name: "Attach", exact: true })
        .click();
      await expect(page.getByText(new RegExp(f.sha256.slice(0, 12))))
        .toBeVisible({ timeout: 15000 });
    }

    // sign & submit
    await page.getByLabel("Signature").fill("Dr. Demo");
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ }))
      .toBeVisible({ timeout: 15000 });
    const rxNum = (await page.locator("h2").first().innerText())
      .split(" ")[0];
    await signOut(page);

    // ---------- lab: receive -> produce -> ship ----------
    await signIn(page, LA_TECH.email, LA_TECH.password);
    await page.locator("tbody tr", { hasText: rxNum }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ }))
      .toBeVisible({ timeout: 15000 });
    // both attachments visible to the lab
    for (const f of [FIX.upperBasic, FIX.lowerBasic]) {
      await expect(page.getByText(
        new RegExp(f.sha256.slice(0, 12)))).toBeVisible({ timeout: 15000 });
    }
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 15000 }),
      page.getByRole("button", { name: "Download & Check-in" }).click()]);
    expect((await download.path())).toBeTruthy();
    await expect(page.getByRole("heading", { name: /— Checked-In/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Mark complete" }).click();
    await expect(page.getByRole("heading", { name: /— Completed/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "QC pass" }).click();
    await page.getByLabel("Carrier").fill("FedEx-UAT");
    await page.getByLabel("Tracking number").fill("FX-UAT-001");
    await page.getByRole("button", { name: "Ship" }).click();
    await expect(page.getByRole("status")).toContainText("Shipped");
    await signOut(page);

    // ---------- practice: receive -> deliver ----------
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.locator("tbody tr", { hasText: rxNum }).click();
    await page.getByRole("button", { name: "Confirm receipt" }).click();
    await expect(page.getByRole("status")).toContainText("Received");
    await page.getByRole("button", { name: "Confirm delivery" }).click();
    await expect(page.getByRole("status")).toContainText("Delivered");
    await expect(page.getByTestId("fulfillment-status"))
      .toContainText("delivered", { timeout: 15000 });
  });
});
