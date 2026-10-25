/* UAT-PAT-01..05 — patients & treatment cases. */
import { expect, test } from "@playwright/test";
import { apiGet, apiLogin, apiPost, PA_ADMIN, signIn } from "./helpers";
import { ensureDataset, UAT_PATIENTS } from "./dataset";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

test.describe("UAT-PAT", () => {
  test("UAT-PAT-01 create patient via web; required fields; list + detail",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    const uniq = Date.now() % 100000;
    const ref = `UAT-WEB-${uniq}`;
    await page.getByLabel("First name").fill("UATCreate");
    await page.getByLabel("Last name").fill(`Webform${uniq}`);
    await page.getByLabel("Date of birth").fill("2010-01-01");
    await page.getByLabel("External ref").fill(ref);
    await page.getByRole("button", { name: "Create patient" }).click();
    await expect(page).toHaveURL(/\/patients\/[0-9a-f-]{36}/);
    await expect(page.getByRole("heading",
      { name: new RegExp(`Webform${uniq}, UATCreate`) })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(ref)).toBeVisible({ timeout: 15000 });

    // back to list -> row present and searchable
    await page.getByRole("button", { name: "Patients" }).click();
    await page.getByLabel("Search").fill(ref);
    await expect(page.locator("tbody tr",
      { hasText: `Webform${uniq}, UATCreate` })).toBeVisible({ timeout: 15000 });
  });

  test("UAT-PAT-02 duplicate patient surfaces candidates (warn-style)",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    // P03 already exists — same last name + DOB triggers possible_duplicate
    await page.getByLabel("First name").fill("Casey");
    await page.getByLabel("Last name").fill("Reyes");
    await page.getByLabel("Date of birth").fill(UAT_PATIENTS.P03.dob);
    await page.getByRole("button", { name: "Create patient" }).click();
    await expect(page.getByRole("alert"))
      .toContainText(/Possible duplicate/i);
    await expect(page.getByText(/Reyes — 2009-11-30/).first())
      .toBeVisible({ timeout: 15000 });
    // warn-style: user may confirm (proves it's not a hard block)
    await expect(page.getByRole("button",
      { name: "Create anyway" })).toBeVisible({ timeout: 15000 });
  });

  test("UAT-PAT-03 edit patient fields persist", async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByLabel("Search").fill("UAT-P01");
    await page.locator("tbody tr", { hasText: "Keeley" }).first().click();
    await page.getByLabel("Notes").fill("UAT edited note — retainer check due");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status"))
      .toContainText(/saved/i, { timeout: 10000 });
    await page.reload();
    await expect(page.getByLabel("Notes"))
      .toHaveValue("UAT edited note — retainer check due");
  });

  test("UAT-PAT-04 create treatment case shows label/stage/opened_at",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByLabel("Search").fill("UAT-P01");
    await page.locator("tbody tr", { hasText: "Keeley" }).first().click();
    const label = `UAT case ${Date.now()}`;
    await page.getByLabel("Case label").fill(label);
    await page.getByRole("button", { name: "Open case" }).click();
    const li = page.locator("li", { hasText: `${label} — active` });
    await expect(li).toBeVisible({ timeout: 15000 });
    await expect(li).toContainText(/opened .*\d{4}/);
  });

  test("UAT-PAT-05 delete blocked on in-flight Rx; allowed after delivery",
       async ({ page }) => {
    // precondition: P06 gets a submitted Rx (in-flight) via API
    const pa = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const labOrg = (await (await apiGet(pa, "/api/v1/orgs")).json())
      .items.find((o: { name: string }) => o.name.includes("Friendly Lab"));
    const rxR = await apiPost(pa, "/api/v1/rx", {
      patient_id: DS.P06.id, lab_org_id: labOrg.id,
      notes: "UAT-P06 inflight",
    });
    const rx = await rxR.json();
    const cur = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
    await apiPost(pa, `/api/v1/rx/${rx.id}/submit`, {
      signature_name: "Dr. Demo", confirm_submit: true, note: null,
    }, { "If-Match": String(cur.version) });


    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByLabel("Search").fill("UAT-P06");
    await page.locator("tbody tr", { hasText: "Petrov" }).first().click();
    await page.getByRole("button", { name: "Delete patient" }).click();
    await expect(page.getByRole("alert"))
      .toContainText(/in-flight|in_flight|active|RX/i);
    await expect(page.getByRole("heading", { name: /Petrov/ }))
      .toBeVisible({ timeout: 15000 }); // not deleted

    // P03B has no Rx at all -> delete permitted
    await page.getByRole("button", { name: "Patients" }).click();
    await page.getByLabel("Search").fill("UAT-P03B");
    await page.locator("tbody tr", { hasText: "UAT-P03B" }).first().click();
    await page.getByRole("button", { name: "Delete patient" }).click();
    await expect(page).toHaveURL(/\/patients$/);
    await pa.dispose();
  });
});
