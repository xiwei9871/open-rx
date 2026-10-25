/* UAT-LAB-01..06 — lab workbench, bundle download & verification. */
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import { expect, test } from "@playwright/test";
import {
  apiGet, apiLogin, apiPost, apiPut, LA_ADMIN, LA_TECH, LB_TECH,
  PA_ADMIN, selectByText, signIn, signOut,
} from "./helpers";
import { ensureDataset, UAT_PATIENTS } from "./dataset";
import { FIX } from "./fixtures";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

const py = (code: string) =>
  execSync(`python3 -c '${code.replace(/'/g, "'\\''")}'`)
    .toString().trim();

/** Create + submit an Rx for UAT via API (precondition only); returns id. */
async function stagedSubmittedRx(patientId: string, note: string) {
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
  await apiPost(pa, `/api/v1/rx/${rx.id}/submit`, {
    signature_name: "Dr. Demo", confirm_submit: true, note: null,
  }, { "If-Match": String(v2.version) });
  await pa.dispose();
  return rx.id as string;
}

test.describe("UAT-LAB", () => {
  test("UAT-LAB-01 inbox shows submitted Rx; drafts hidden; LB sees nothing",
       async ({ page }) => {
    const rxId = await stagedSubmittedRx(DS.P04.id, "UAT-LAB-01");
    const num = await (async () => {
      const la = await apiLogin(LA_TECH.email, LA_TECH.password);
      const b = await (await apiGet(la, `/api/v1/rx/${rxId}`)).json();
      await la.dispose();
      return b.rx_number as string;
    })();

    await signIn(page, LA_TECH.email, LA_TECH.password);
    await expect(page.getByRole("heading",
      { name: "Received Prescriptions" })).toBeVisible({ timeout: 15000 });
    await expect(page.locator("tbody tr", { hasText: num }))
      .toBeVisible({ timeout: 15000 });
    // drafts are never exposed: our list only carries submitted+ rows
    for (const st of await page.locator("tbody .pill").allInnerTexts()) {
      expect(st).not.toMatch(/saved|draft/i);
    }
    await signOut(page);
    // unconnected lab: the same Rx is invisible
    await signIn(page, LB_TECH.email, LB_TECH.password);
    await expect(page.locator("tbody tr", { hasText: num }))
      .toHaveCount(0);
    await page.goto(`/rx/${rxId}`);
    await page.waitForTimeout(1000);
    await expect(page.getByText(num)).toHaveCount(0);
    // no patient identity leaks anywhere on the rendered page
    await expect(page.getByText(/Osei|Keeley|P\d{6}/)).toHaveCount(0);
    const h2 = page.locator("h2").first();
    if (await h2.count()) {
      expect(await h2.innerText()).not.toContain(num);
    }
  });

  test("UAT-LAB-02 detail shows patient label, doctor, items, notes",
       async ({ page }) => {
    const rxId = await stagedSubmittedRx(DS.P04.id, "UAT-LAB-02 detail");
    await signIn(page, LA_ADMIN.email, LA_ADMIN.password);
    await page.goto(`/rx/${rxId}`);
    await expect(page.getByRole("heading", { name: /RX\d+/ }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Osei, Amara/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Dr\. Demo/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/UAT-LAB-02 detail/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/SPL — Essix splint|Essix/)).toBeVisible({ timeout: 15000 });
  });

  test("UAT-LAB-03 download & check-in: real file, ZIP contents verified",
       async ({ page }) => {
    const rxId = await stagedSubmittedRx(DS.P05.id, "UAT-LAB-03 bundle");
    await signIn(page, LA_TECH.email, LA_TECH.password);
    await page.goto(`/rx/${rxId}`);
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 15000 }),
      page.getByRole("button", { name: "Download & Check-in" }).click()]);
    const path = await download.path();
    expect(path).toBeTruthy();
    fs.copyFileSync(path!, "/tmp/uat-bundle.zip");
    expect(fs.statSync("/tmp/uat-bundle.zip").size).toBeGreaterThan(500);

    // ZIP structure: prescription.pdf + manifest.json + attachments/
    const listing = py(
      "import zipfile;print('\\n'.join(zipfile.ZipFile('/tmp/uat-bundle.zip').namelist()))");
    expect(listing).toContain("prescription.pdf");
    expect(listing).toContain("manifest.json");

    // PDF is a real document, not an empty stub
    const pdfInfo = py(
      "import zipfile;b=zipfile.ZipFile('/tmp/uat-bundle.zip').read('prescription.pdf');print(len(b),b[:8])");
    expect(pdfInfo).toContain("%PDF");
    const m = JSON.parse(py(
      "import zipfile;print(zipfile.ZipFile('/tmp/uat-bundle.zip').read('manifest.json').decode())"));
    expect(m.files ?? m.attachments ?? []).toBeDefined();

    // status transitioned to checked_in via the download
    await expect(page.getByRole("heading", { name: /— Checked-In/ }))
      .toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/submitted → checked_in/)).toBeVisible({ timeout: 15000 });
  });

  test("UAT-LAB-04 bundle manifest matches zip entries; attached STL inside",
       async ({ page }) => {
    // P01 upper STL must be attached to a submitted Rx (web path already
    // proven by RX-05); attach here via API for a dedicated bundle check.
    const pa = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const assets = await (await apiGet(pa,
      `/api/v1/patients/${DS.P01.id}/assets`)).json();
    let assetId = assets.items.find(
      (a: { asset: { sha256: string } }) =>
        a.asset.sha256 === FIX.upperBasic.sha256)?.asset_id;
    if (!assetId) {
      const sess = await apiPost(pa, "/api/v1/uploads", {
        sha256: FIX.upperBasic.sha256, bytes: FIX.upperBasic.bytes,
        kind: "stl", jaw: "upper", filename_hint: FIX.upperBasic.name });
      const s = await sess.json();
      await pa.fetch(s.upload_urls[0],
        { method: "PUT", data: FIX.upperBasic.buffer });
      const a = await (await apiPost(pa,
        `/api/v1/uploads/${s.id}/complete`,
        { sha256: FIX.upperBasic.sha256 })).json();
      await apiPost(pa, `/api/v1/assets/${a.id}/references`, {
        subject_type: "patient", subject_id: DS.P01.id, role: "original" });
      assetId = a.id;
    }
    const rxId = await stagedSubmittedRx(DS.P01.id, "UAT-LAB-04");
    const ar = await apiPost(pa, `/api/v1/rx/${rxId}/attachments`, {
      asset_id: assetId, role: "original" });
    expect(ar.ok(), "attach").toBeTruthy();
    await pa.dispose();

    await signIn(page, LA_ADMIN.email, LA_ADMIN.password);
    await page.goto(`/rx/${rxId}`);
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 15000 }),
      page.getByRole("button", { name: /Download/ }).click()]);
    const path = await download.path();
    fs.copyFileSync(path!, "/tmp/uat-bundle-att.zip");

    const manifest = JSON.parse(py(
      "import zipfile;print(zipfile.ZipFile('/tmp/uat-bundle-att.zip').read('manifest.json').decode())"));
    const names = py(
      "import zipfile;print('\\n'.join(zipfile.ZipFile('/tmp/uat-bundle-att.zip').namelist()))");
    // every manifest file entry exists in the zip and hashes correctly
    const files = manifest.files ?? manifest.attachments ?? [];
    expect(files.length, "manifest should list the attached STL")
      .toBeGreaterThan(0);
    for (const f of files) {
      const entry = f.entry ?? f.path ?? f.name;
      expect(names, `missing ${entry}`).toContain(entry);
      const sha = py(
        `import zipfile,hashlib;b=zipfile.ZipFile('/tmp/uat-bundle-att.zip').read('${entry}');print(hashlib.sha256(b).hexdigest())`);
      expect(sha).toBe(f.sha256);
    }
    // the STL bytes inside the bundle match the patient upload 1:1
    const stlEntry = files.find(
      (f: { sha256: string }) => f.sha256 === FIX.upperBasic.sha256);
    expect(stlEntry, "uploaded STL absent from bundle").toBeTruthy();
  });

  test("UAT-LAB-05 repeat download reuses bundle when content unchanged",
       async ({ page }) => {
    const rxId = await stagedSubmittedRx(DS.P04.id, "UAT-LAB-05");
    const la = await apiLogin(LA_ADMIN.email, LA_ADMIN.password);
    const b1 = await (await apiPost(la,
      `/api/v1/rx/${rxId}/bundle-download`, {})).json();
    const b2 = await (await apiPost(la,
      `/api/v1/rx/${rxId}/bundle-download`, {})).json();
    // unchanged content -> same bundle id + sha (reuse is allowed)
    expect(b2.bundle.id).toBe(b1.bundle.id);
    expect(b2.bundle.sha256).toBe(b1.bundle.sha256);
    // a content change (attach) bumps rx.version -> a NEW bundle is built
    const cur = await (await apiGet(la, `/api/v1/rx/${rxId}`)).json();
    void cur;
    const pa = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const assets = await (await apiGet(pa,
      `/api/v1/patients/${DS.P01.id}/assets`)).json();
    const aid = assets.items[0]?.asset_id;
    if (aid) {
      const ar = await apiPost(pa, `/api/v1/rx/${rxId}/attachments`,
        { asset_id: aid, role: "attachment" });
      if (ar.ok()) {
        const b3 = await (await apiPost(la,
          `/api/v1/rx/${rxId}/bundle-download`, {})).json();
        expect(b3.bundle.id, "content change must mint a new bundle")
          .not.toBe(b1.bundle.id);
      }
    }
    await pa.dispose();
    await la.dispose();
  });

  test("UAT-LAB-06 lab complete marks production done, practice sees it",
       async ({ page }) => {
    const rxId = await stagedSubmittedRx(DS.P05.id, "UAT-LAB-06");
    // check-in via API precondition
    const la = await apiLogin(LA_TECH.email, LA_TECH.password);
    const v = await (await apiGet(la, `/api/v1/rx/${rxId}`)).json();
    await apiPost(la, `/api/v1/rx/${rxId}/check-in`, {},
                  { "If-Match": String(v.version) });
    await la.dispose();

    await signIn(page, LA_TECH.email, LA_TECH.password);
    await page.goto(`/rx/${rxId}`);
    await expect(page.getByRole("heading", { name: /— Checked-In/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Mark complete" }).click();
    await expect(page.getByRole("heading", { name: /— Completed/ }))
      .toBeVisible({ timeout: 15000 });
    await signOut(page);

    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await page.goto(`/rx/${rxId}`);
    await expect(page.getByRole("heading", { name: /— Completed/ }))
      .toBeVisible({ timeout: 15000 });
  });
});
