/* UAT-NEG-01..05 — permission & failure guardrails. */
import { expect, test } from "@playwright/test";
import {
  apiGet, apiLogin, apiPost, apiPut, LA_TECH, LB_TECH, PA_ADMIN, PA_STAFF,
  pickPatient, selectByText, signIn,
} from "./helpers";
import { ensureDataset } from "./dataset";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

test.describe("UAT-NEG", () => {
  test.describe.configure({ timeout: 60000 });
  test("UAT-NEG-01 unconnected-lab deep link leaks nothing", async ({ page }) => {
    // submitted Rx owned by PA/LA — LB must not see it
    const pa = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const labOrg = (await (await apiGet(pa, "/api/v1/orgs")).json())
      .items.find((o: { name: string }) => o.name.includes("Friendly Lab"));
    const spl = (await (await apiGet(pa, "/api/v1/catalog/appliances"))
      .json()).items.find((i: { code: string }) => i.code === "SPL");
    const rx = await (await apiPost(pa, "/api/v1/rx", {
      patient_id: DS.P04.id, lab_org_id: labOrg.id, notes: "NEG-01",
    })).json();
    const v1 = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
    await apiPut(pa, `/api/v1/rx/${rx.id}/items`, { items: [{
      appliance_id: spl.id, arch: "upper", tooth_ops: [],
      options: null, qty: 1 }] }, { "If-Match": String(v1.version) });
    const v2 = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
    await apiPost(pa, `/api/v1/rx/${rx.id}/submit`, {
      signature_name: "Dr. Demo", confirm_submit: true, note: null,
    }, { "If-Match": String(v2.version) });
    await pa.dispose();

    await signIn(page, LB_TECH.email, LB_TECH.password);
    await page.goto(`/rx/${rx.id}`);
    await page.waitForTimeout(800);
    await expect(page.getByText(/Osei|UAT-|RX\d{6,}/)).toHaveCount(0);
    // API check too
    const lb = await apiLogin(LB_TECH.email, LB_TECH.password);
    const r = await apiGet(lb, `/api/v1/rx/${rx.id}`);
    expect([403, 404]).toContain(r.status());
    await lb.dispose();
  });

  test("UAT-NEG-02 practice cannot run lab-only actions", async ({ page }) => {
    const pa = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const rx = await (await apiPost(pa, "/api/v1/rx", {
      patient_id: DS.P01.id, notes: "NEG-02" })).json();
    // practice-side lab endpoints are refused
    const v = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
    for (const [ep, body] of [["check-in", {}], ["complete", {}],
        ["qc", { result: "pass" }], ["ship", { carrier: "x", tracking_number: "1" }]] as const) {
      const r = await apiPost(pa, `/api/v1/rx/${rx.id}/${ep}`, body,
                              { "If-Match": String(v.version) });
      expect([403, 409, 422], `${ep} must be refused for practice`)
        .toContain(r.status());
    }
    await pa.dispose();

    // web: lab-only buttons simply do not render for a practice user
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.goto(`/rx/${rx.id}`);
    await expect(page.getByRole("button", { name: "Check in" }))
      .toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mark complete" }))
      .toHaveCount(0);
    await expect(page.getByRole("button", { name: "QC pass" }))
      .toHaveCount(0);
    await expect(page.getByRole("button", { name: "Ship" }))
      .toHaveCount(0);
  });

  test("UAT-NEG-03 double-clicks create no duplicate side effects",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("button", { name: "New Rx" }).click();
    await pickPatient(page, /Keeley, Jordan/);
    await selectByText(page, "Laboratory", "Friendly Lab");
    await selectByText(page, "Doctor", "Dr. Demo");
    await selectByText(page, "catalog", "Hawley retainer");
    await page.getByRole("button", { name: "Add item" }).click();
    // hammer the save button with two clicks in one JS tick — the second
    // dispatchEvent would wait forever once the first save navigates away.
    const save = page.getByRole("button", { name: "Save draft" });
    await save.evaluate((el) => {
      (el as HTMLElement).click(); (el as HTMLElement).click();
    });
    await page.waitForTimeout(1500);
    // one Rx created — detail page (not an error / duplicate list row)
    await expect(page.getByRole("heading", { name: /RX\d+ — Saved/ }))
      .toBeVisible({ timeout: 15000 });

    // comment double-click
    const stamp = `dup-${Date.now()}`;
    await page.locator("input[name=comment]").fill(stamp);
    const post = page.getByRole("button", { name: "Post" });
    await post.evaluate((el) => {
      (el as HTMLElement).click(); (el as HTMLElement).click();
    });
    await page.waitForTimeout(1200);
    expect(await page.getByText(stamp).count()).toBeLessThanOrEqual(1);
  });

  test("UAT-NEG-04 API outage surfaces an explicit error, never silent",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.route("**/api/**", (r) => r.abort());
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10000 });
    await page.unroute("**/api/**");
    // recovery: navigating again loads normally
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await expect(page.locator("tbody tr").first()).toBeVisible({ timeout: 15000 });
  });

  test("UAT-NEG-05 back/forward honours URL routing", async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await expect(page).toHaveURL(/\/patients/);
    await page.locator("tbody tr").first().click();
    await expect(page).toHaveURL(/\/patients\/[0-9a-f-]{36}/);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await expect(page).toHaveURL(/\/rx/);
    await page.goBack();
    await expect(page).toHaveURL(/\/patients\/[0-9a-f-]{36}/);
    await page.goBack();
    await expect(page).toHaveURL(/\/patients$/);
    await page.goForward();
    await expect(page).toHaveURL(/\/patients\/[0-9a-f-]{36}/);
  });
});
