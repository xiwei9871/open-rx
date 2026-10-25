/* UAT-RX-01..10 — practice-side prescription authoring. */
import { expect, test } from "@playwright/test";
import {
  apiGet, apiLogin, apiPost, apiPut, LA_TECH, PA_ADMIN, pickPatient,
  selectByText, signIn, signOut,
} from "./helpers";
import { ensureDataset, UAT_PATIENTS } from "./dataset";
import { FIX, pwFile } from "./fixtures";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

async function openRxCreate(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await page.getByRole("button", { name: "New Rx" }).click();
}

async function fillOrderBasics(page: import("@playwright/test").Page,
                               ref: keyof typeof UAT_PATIENTS) {
  await pickPatient(page,
    new RegExp(`${UAT_PATIENTS[ref].last}, ${UAT_PATIENTS[ref].first}`));
  await selectByText(page, "Laboratory", "Friendly Lab");
  await selectByText(page, "Doctor", "Dr. Demo");
  // location is optional in the seeded org — pick one when offered
  const loc = page.getByLabel("Location");
  if (await loc.locator("option").count() > 1) {
    const v = await loc.locator("option").nth(1).getAttribute("value");
    if (v) await loc.selectOption(v);
  }
  await page.getByLabel("Due date").fill("2030-06-30");
  await page.getByLabel("Notes").fill(`UAT note for ${ref}`);
}

test.describe("UAT-RX practice", () => {
  test.describe.configure({ timeout: 60000 });
  test("UAT-RX-01 create draft: patient/lab/doctor/location/due/notes",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    // patient select shows UAT dataset entries
    await pickPatient(page, /Keeley, Jordan \(P\d+\)/);
    // treatment case select appears once a patient is chosen
    await expect(page.getByLabel("Treatment case")).toBeVisible({ timeout: 15000 });
    await selectByText(page, "Laboratory", "Friendly Lab");
    await selectByText(page, "Doctor", "Dr. Demo");
    // location is optional in this seed — pick whatever is offered
    const loc = page.getByLabel("Location");
    if (await loc.locator("option").count() > 1) {
      const v = await loc.locator("option").nth(1).getAttribute("value");
      if (v) await loc.selectOption(v);
    }
    await page.getByLabel("Due date").fill("2030-06-30");
    await page.getByLabel("Notes").fill("UAT-RX-01 draft");
    await selectByText(page, "catalog", "Hawley retainer");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading",
      { name: /RX\d+ — Saved/ })).toBeVisible({ timeout: 15000 });
  });

  test("UAT-RX-02 required option part blocks add until filled",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    await selectByText(page, "catalog", "Molar band");
    // required option row renders
    await expect(page.getByLabel("Option band_tooth")).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Add item" }).click();
    await expect(page.getByRole("alert"))
      .toContainText(/band_tooth/);
    await page.getByLabel("Option band_tooth").fill("16");
    await page.getByRole("button", { name: "Add item" }).click();
    await expect(page.getByText(/BND — Molar band \(Upper arch\) — band_tooth=16/))
      .toBeVisible({ timeout: 15000 });
  });

  test("UAT-RX-03 tooth ops persist across draft reopen",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    await fillOrderBasics(page, "P02");
    await selectByText(page, "catalog", "Rapid palatal expander");
    await page.getByRole("button", { name: "Add item" }).click();
    // the tooth grid auto-expands on add; the "teeth N" button toggles it
    const t14 = page.getByRole("button", { name: "tooth 14" });
    await t14.waitFor({ timeout: 3000 }).catch(async () => {
      await page.getByRole("button", { name: "teeth 0" }).click();
    });
    await t14.click();
    await page.getByRole("button", { name: "tooth 24" }).click();
    await expect(page.getByText("14:reset  24:reset")).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });
    // draft reopened -> tooth ops shown on items
    await expect(page.getByText(/reset 14.*reset 24|14.*24/)).toBeVisible({ timeout: 15000 });
  });

  test("UAT-RX-04 template save/apply; editing new Rx leaves template intact",
       async ({ page }) => {
    const tname = `UAT-tmpl-${Date.now()}`;
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    await selectByText(page, "catalog", "Hawley retainer");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByLabel("Notes").fill("template notes");
    await page.getByLabel("Template name").fill(tname);
    await page.getByRole("button",
      { name: "Save items as template" }).click();
    await expect(page.getByRole("status"))
      .toContainText("Template saved");

    // apply to a new Rx, then diverge
    await openRxCreate(page);
    await selectByText(page, "Template", tname);
    await expect(page.getByText(/HWL — Hawley retainer \(Upper arch\)/))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "remove" }).click();
    await selectByText(page, "catalog", "Essix splint");
    await page.getByRole("button", { name: "Add item" }).click();
    await fillOrderBasics(page, "P02");
    await page.getByLabel("Notes").fill("diverged");
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });

    // source template payload unchanged (API check: still 1 item, HWL)
    const api = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const tmpls = await (await apiGet(api, "/api/v1/templates")).json();
    const t = tmpls.items.find((x: { name: string }) => x.name === tname);
    expect(t, "template lost").toBeTruthy();
    expect(t.payload.items).toHaveLength(1);
    expect(t.payload.notes).toBe("template notes");
    await api.dispose();
  });

  test("UAT-RX-05 attach patient STL to Rx from the web",
       async ({ page }) => {
    // precondition: P01 has an upper STL (from ASSET-01 or fresh upload)
    const api = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const existing = await (await apiGet(api,
      `/api/v1/patients/${DS.P01.id}/assets`)).json();
    if (!existing.items.length) {
      const sess = await apiPost(api, "/api/v1/uploads", {
        sha256: FIX.upperBasic.sha256, bytes: FIX.upperBasic.bytes,
        kind: "stl", jaw: "upper", filename_hint: FIX.upperBasic.name,
      });
      const s = await sess.json();
      await api.fetch(s.upload_urls[0],
        { method: "PUT", data: FIX.upperBasic.buffer });
      const asset = await (await apiPost(api,
        `/api/v1/uploads/${s.id}/complete`,
        { sha256: FIX.upperBasic.sha256 })).json();
      await apiPost(api, `/api/v1/assets/${asset.id}/references`, {
        subject_type: "patient", subject_id: DS.P01.id, role: "original" });
    }
    // draft Rx on P01
    const rx = await (await apiPost(api, "/api/v1/rx", {
      patient_id: DS.P01.id, notes: "UAT-RX-05 attach",
    })).json();
    await api.dispose();

    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.goto(`/rx/${rx.id}`);
    await expect(page.getByRole("heading", { name: "Attachments" }))
      .toBeVisible({ timeout: 15000 });
    await selectByText(page, "Patient file", /stl\/upper/);
    await page.getByRole("button", { name: "Attach", exact: true }).click();
    await expect(page.getByRole("status"))
      .toContainText("File attached");
    await expect(page.getByText(/stl\/upper — original/)).toBeVisible({ timeout: 15000 });
  });

  test("UAT-RX-06 draft survives logout + fresh login",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    await fillOrderBasics(page, "P01");
    await selectByText(page, "catalog", "Essix splint");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });
    const url = page.url();

    await signOut(page);
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.goto(url);
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("cell", { name: /UAT note for P01/ }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Jun 30, 2030|2030-06-30/).first())
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/SPL — Essix splint \(Upper arch\)/))
      .toBeVisible({ timeout: 15000 });
  });

  test("UAT-RX-07 submit blocked without items/lab; message readable",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    await pickPatient(page, /Keeley, Jordan \(P\d+\)/);
    // no lab, no items -> save draft works, submit must not
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("alert"))
      .toContainText(/laboratory|part|appliance|required/i);
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 }); // stayed draft
  });

  test("UAT-RX-08 submit records signature + transition", async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    await fillOrderBasics(page, "P01");
    await selectByText(page, "catalog", "Hawley retainer");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });
    const rxId = page.url().split("/").pop()!;
    await page.getByLabel("Signature").fill("Dr. Demo");
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("cell", { name: /Dr\. Demo \(v\d+\)/ }))
      .toBeVisible({ timeout: 15000 });
    // transition history recorded
    const api = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const tr = await (await apiGet(api,
      `/api/v1/rx/${rxId}/transitions`)).json();
    const subs = tr.items.filter(
      (t: { to_status: string }) => t.to_status === "submitted");
    expect(subs.length).toBeGreaterThan(0);
    const body = await (await apiGet(api, `/api/v1/rx/${rxId}`)).json();
    expect(body.signature_name).toBe("Dr. Demo");
    expect(body.signed_rx_version).toBeGreaterThan(0);
    expect(body.submitted_at).toBeTruthy();
    await api.dispose();
  });

  test("UAT-RX-09 unsubmit -> draft -> edit -> resubmit", async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openRxCreate(page);
    await fillOrderBasics(page, "P01");
    await selectByText(page, "catalog", "Essix splint");
    await page.getByRole("button", { name: "Add item" }).click();
    await page.getByRole("button", { name: "Save draft" }).click();
    await page.getByLabel("Signature").fill("Dr. Demo");
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Unsubmit" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });
    // edit + resubmit works
    await page.getByLabel("Notes").fill("edited after unsubmit");
    await page.getByRole("button", { name: "Save" }).first().click();
    await expect(page.getByRole("status")).toBeVisible({ timeout: 15000 });
    await page.getByLabel("Signature").fill("Dr. Demo");
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ }))
      .toBeVisible({ timeout: 15000 });
  });

  test("UAT-RX-10 unsubmit rejected after lab check-in", async ({ page }) => {
    // precondition: submitted Rx for lab to check in
    const pa = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const la = await apiLogin(LA_TECH.email, LA_TECH.password);
    const labOrg = (await (await apiGet(pa, "/api/v1/orgs")).json())
      .items.find((o: { name: string }) => o.name.includes("Friendly Lab"));
    const rx = await (await apiPost(pa, "/api/v1/rx", {
      patient_id: DS.P02.id, lab_org_id: labOrg.id,
      notes: "UAT-RX-10",
    })).json();
    const cur = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
    // add one item via replace-items (draft; wire name is appliance_id)
    await apiPut(pa, `/api/v1/rx/${rx.id}/items`, { items: [{
      appliance_id: (await (await apiGet(pa,
        "/api/v1/catalog/appliances")).json())
        .items.find((i: { code: string }) => i.code === "SPL").id,
      arch: "upper", tooth_ops: [], options: null, qty: 1 }] },
      { "If-Match": String(cur.version) });

    const cur2 = await (await apiGet(pa, `/api/v1/rx/${rx.id}`)).json();
    await apiPost(pa, `/api/v1/rx/${rx.id}/submit`, {
      signature_name: "Dr. Demo", confirm_submit: true, note: null,
    }, { "If-Match": String(cur2.version) });
    // lab checks in through the real endpoint
    const cur3 = await (await apiGet(la, `/api/v1/rx/${rx.id}`)).json();
    const ci = await apiPost(la, `/api/v1/rx/${rx.id}/check-in`, {},
                             { "If-Match": String(cur3.version) });
    expect(ci.ok(), "check-in precondition").toBeTruthy();
    await la.dispose();

    // browser: practice sees unsubmit is rejected with a readable message
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.goto(`/rx/${rx.id}`);
    await expect(page.getByRole("heading", { name: /— Checked-In/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Unsubmit" }).click();
    await expect(page.getByRole("alert"))
      .toContainText(/checked in/i);
    await expect(page.getByRole("heading", { name: /— Checked-In/ }))
      .toBeVisible({ timeout: 15000 });
    await pa.dispose();
  });
});
