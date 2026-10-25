/* UAT-FULFILL-01..05 — QC -> ship -> receive -> deliver closure + dashboard. */
import { expect, test } from "@playwright/test";
import {
  apiGet, apiLogin, apiPost, apiPut, LA_TECH, PA_ADMIN, signIn, signOut,
} from "./helpers";
import { ensureDataset } from "./dataset";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

async function checkedInRx(patientId: string, note: string) {
  const pa = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
  const labOrg = (await (await apiGet(pa, "/api/v1/orgs")).json())
    .items.find((o: { name: string }) => o.name.includes("Friendly Lab"));
  const spl = (await (await apiGet(pa, "/api/v1/catalog/appliances"))
    .json()).items.find((i: { code: string }) => i.code === "SPL");
  const rx = await (await apiPost(pa, "/api/v1/rx", {
    patient_id: patientId, lab_org_id: labOrg.id, notes: note,
  })).json();
  const v1 = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
  await apiPut(pa, `/api/v1/rx/${rx.id}/items`, { items: [{
    appliance_id: spl.id, arch: "upper", tooth_ops: [],
    options: null, qty: 1 }] }, { "If-Match": String(v1.version) });
  const v2 = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
  const sub = await apiPost(pa, `/api/v1/rx/${rx.id}/submit`, {
    signature_name: "Dr. Demo", confirm_submit: true, note: null,
  }, { "If-Match": String(v2.version) });
  expect(sub.ok(), "submit precondition").toBeTruthy();
  const la = await apiLogin(LA_TECH.email, LA_TECH.password);
  const v3 = await (await apiGet(la, `/api/v1/rx/${rx.id}`)).json();
  const ci = await apiPost(la, `/api/v1/rx/${rx.id}/check-in`, {},
                           { "If-Match": String(v3.version) });
  expect(ci.ok(), "check-in precondition").toBeTruthy();
  const v4 = await (await apiGet(la, `/api/v1/rx/${rx.id}`)).json();
  const cp = await apiPost(la, `/api/v1/rx/${rx.id}/complete`, {},
                           { "If-Match": String(v4.version) });
  expect(cp.ok(), "complete precondition").toBeTruthy();
  await la.dispose(); await pa.dispose();
  return rx.id as string;
}

test.describe("UAT-FULFILL", () => {
  test("UAT-FULFILL-01..04 QC->ship->receive->deliver full loop on web",
       async ({ page }) => {
    const rxId = await checkedInRx(DS.P05.id, "UAT-FULFILL web loop");
    // lab: QC pass then ship
    await signIn(page, LA_TECH.email, LA_TECH.password);
    await page.goto(`/rx/${rxId}`);
    await expect(page.getByRole("heading", { name: /— Completed/ }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText("qc_pending")).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "QC pass" }).click();
    await expect(page.getByRole("status"))
      .toContainText("QC passed recorded");
    await page.getByLabel("Carrier").fill("UPS-UAT");
    await page.getByLabel("Tracking number").fill("1ZUAT999");
    await page.getByRole("button", { name: "Ship" }).click();
    await expect(page.getByRole("status")).toContainText("Shipped");
    await expect(page.getByRole("cell", { name: "UPS-UAT" }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/1ZUAT999/).first())
      .toBeVisible({ timeout: 15000 });
    await signOut(page);

    // practice: receive then deliver
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.goto(`/rx/${rxId}`);
    await expect(page.getByTestId("fulfillment-status"))
      .toContainText("shipped", { timeout: 15000 });
    await page.getByRole("button", { name: "Confirm receipt" }).click();
    await expect(page.getByRole("status")).toContainText("Received");
    await expect(page.getByTestId("fulfillment-status"))
      .toContainText("received", { timeout: 15000 });
    await page.getByRole("button", { name: "Confirm delivery" }).click();
    await expect(page.getByRole("status")).toContainText("Delivered");
    await expect(page.getByTestId("fulfillment-status"))
      .toContainText("delivered", { timeout: 15000 });
    // delivered_at recorded
    const body = await page.request.get(`/api/v1/rx/${rxId}`);
    const rx = await body.json();
    expect(rx.shipped_at).toBeTruthy();
    expect(rx.received_at).toBeTruthy();
    expect(rx.delivered_at).toBeTruthy();
  });

  test("UAT-FULFILL-05 dashboard + status filters show lifecycle states",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    // stat strip exists with meaningful counters
    await expect(page.locator("[data-testid=dashboard]")).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Total shown")).toBeVisible({ timeout: 15000 });
    // fulfillment filter offers lifecycle states
    const ff = page.locator("label", { hasText: "Fulfillment" })
      .locator("select");
    const opts = await ff.locator("option").allInnerTexts();
    expect(opts.join(" ")).toMatch(/qc|ship|deliver/i);
  });
});
