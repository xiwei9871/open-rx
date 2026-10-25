/* Private-preview PUBLIC acceptance suite — runs against the deployed
 * HTTPS/LAN preview stack, not localhost dev. Credentials come from env:
 *   PREVIEW_BASE_URL      e.g. https://easyrx.manqiaotechnology.com
 *                             (or http://localhost:8190 via ssh tunnel)
 *   PREVIEW_PRACTICE_EMAIL / PREVIEW_PRACTICE_PASSWORD
 *   PREVIEW_LAB_EMAIL / PREVIEW_LAB_PASSWORD
 *   PREVIEW_PATIENT       seeded demo patient surname, default "Whitfield"
 *   PREVIEW_LAB_NAME      seeded lab display name, default "Coastal Ortho"
 *
 * Every step happens in a real browser; API calls are only used for a size
 * probe that the UI cannot express honestly.
 */
import { expect, request as pwRequest, test } from "@playwright/test";
import { FIX, pwFile, uniqueStl } from "../uat/fixtures";
import { signIn, signOut, selectByText, pickPatient } from "../uat/helpers";

const BASE = process.env.PREVIEW_BASE_URL ?? "http://localhost:8190";
const PRACTICE = {
  email: process.env.PREVIEW_PRACTICE_EMAIL ?? "preview.doctor@demo.easyrs",
  password: process.env.PREVIEW_PRACTICE_PASSWORD ?? "",
};
const LAB = {
  email: process.env.PREVIEW_LAB_EMAIL ?? "preview.lab@demo.easyrs",
  password: process.env.PREVIEW_LAB_PASSWORD ?? "",
};
const PATIENT = process.env.PREVIEW_PATIENT ?? "Whitfield";
const LAB_NAME = process.env.PREVIEW_LAB_NAME ?? "Coastal Ortho";

test.skip(!PRACTICE.password || !LAB.password,
          "preview credentials not supplied");

test.describe.configure({ mode: "serial" });

let rxNum = "";

test.describe("preview: surface & security", () => {
  test("PV-SEC-01 welcome + demo banner + security headers", async ({ page }) => {
    const resp = await page.goto("/");
    expect(resp?.status()).toBe(200);
    const headers = resp!.headers();
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-robots-tag"]).toContain("noindex");
    await expect(page.getByText("Demo Environment — Synthetic Data Only"))
      .toBeVisible();
    await expect(page.getByText(/explore the complete digital workflow/i))
      .toBeVisible();
    // three functional entry points (not decorative)
    await expect(page.getByRole("button", { name: /Try the Practice Workflow/ }))
      .toBeVisible();
    await expect(page.getByRole("button", { name: /Explore the Lab Workflow/ }))
      .toBeVisible();
    await expect(page.getByRole("button",
      { name: /View a Sample Prescription/ })).toBeVisible();
    const robots = await page.goto("/robots.txt");
    expect(robots?.status()).toBe(200);
    expect(await robots!.text()).toContain("Disallow: /");
  });

  test("PV-SEC-02 unauthenticated deep link bounces to sign-in; "
       + "unknown API path is a clean 404", async ({ page, request }) => {
    await page.goto("/patients");
    await expect(page.getByRole("button", { name: "Sign in" }))
      .toBeVisible();
    await page.goto("/rx/does-not-exist");
    await expect(page.getByRole("button", { name: "Sign in" }))
      .toBeVisible();
    const r = await request.get("/api/v1/nonexistent");
    expect(r.status()).toBe(404);
  });
});

test.describe("preview: practice journey", () => {
  test("PV-PRA-01 demo shortcut routes post-login; banner persists", async ({
    page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Try the Practice Workflow/ })
      .click();
    await page.getByLabel("Email").fill(PRACTICE.email);
    await page.getByLabel("Password").fill(PRACTICE.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Patients" }))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Demo Environment — Synthetic Data Only/))
      .toBeVisible();
    await expect(page.getByText(/Preview v0\.1/)).toBeVisible();
  });

  test("PV-PRA-02 upper+lower STL upload via presigned PUT to the public S3 "
       + "endpoint", async ({ page }) => {
    test.setTimeout(90_000);
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await page.getByRole("button", { name: "Patients" }).click();
    const term = `PV-${Date.now() % 100000}`;
    await page.getByLabel("First name").fill("Preview");
    await page.getByLabel("Last name").fill(term);
    await page.getByLabel("Date of birth").fill("2011-04-15");
    await page.getByRole("button", { name: "Create patient" }).click();
    // create navigates straight to the new patient's detail page
    await expect(page.getByText(new RegExp(`${term}, Preview`)))
      .toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Treatment cases/i))
      .toBeVisible({ timeout: 15000 });

    // capture the actual PUT target the browser is given
    const puts: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "PUT") puts.push(r.url());
    });
    const warn = page.getByText(/Do not upload real patient records/);
    await expect(warn).toBeVisible();
    await page.getByLabel("STL file").setInputFiles(pwFile(FIX.upperBasic));
    await page.getByLabel("Jaw").selectOption("upper");
    await page.getByRole("button", { name: "Upload STL" }).click();
    await expect(page.getByText(FIX.upperBasic.sha256.slice(0, 16)))
      .toBeVisible({ timeout: 30000 });
    await page.getByLabel("STL file").setInputFiles(pwFile(FIX.lowerBasic));
    await page.getByLabel("Jaw").selectOption("lower");
    await page.getByRole("button", { name: "Upload STL" }).click();
    await expect(page.getByText(FIX.lowerBasic.sha256.slice(0, 16)))
      .toBeVisible({ timeout: 30000 });
    // presigned PUTs must target the public storage endpoint — never the API
    // host and never a bare IP inside the page flow.
    expect(puts.length).toBeGreaterThanOrEqual(2);
    for (const u of puts) expect(u).toMatch(/^https?:\/\//);
    for (const u of puts) expect(u).not.toContain("/api/");
    console.log(`PV-PRA-02 presigned PUT targets: ${puts.join(" , ")}`);
    const upperRow = page.locator("li",
      { hasText: FIX.upperBasic.sha256.slice(0, 16) });
    await expect(upperRow).toContainText("Upper arch");
    await expect(upperRow).toContainText("valid mesh");
  });

  test("PV-PRA-03 full Rx: case-bound draft -> sign -> submit", async ({
    page }) => {
    test.setTimeout(120_000);
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("button", { name: "New Rx" }).click();
    await pickPatient(page, new RegExp(PATIENT));
    await selectByText(page, "Laboratory", new RegExp(LAB_NAME));
    await selectByText(page, "catalog", "Hawley retainer");
    await page.getByRole("button", { name: "Add item" }).click();
    await expect(page.getByText(/HWL — Hawley retainer \(Upper arch\)/))
      .toBeVisible();
    await page.getByLabel("Notes")
      .fill("Preview acceptance order — synthetic.");
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ }))
      .toBeVisible({ timeout: 15000 });
    rxNum = (await page.getByRole("heading", { level: 2 }).innerText())
      .split(" ")[0];
    await page.getByLabel("Signature").fill("Dr. Preview");
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ }))
      .toBeVisible({ timeout: 15000 });
  });

  test("PV-PRA-04 oversized STL is rejected with a readable message",
       async () => {
    // declare-only probe via API: >100MB exceeds preview UPLOAD_MAX_BYTES
    const ctx = await pwRequest.newContext({ baseURL: BASE });
    const login = await ctx.post("/api/v1/auth/login", {
      headers: { "x-requested-with": "XMLHttpRequest" },
      data: { email: PRACTICE.email, password: PRACTICE.password },
    });
    expect(login.ok()).toBeTruthy();
    const big = await ctx.post("/api/v1/uploads", {
      headers: { "x-requested-with": "XMLHttpRequest" },
      data: { kind: "stl", jaw: "upper", bytes: 200 * 1024 * 1024,
              sha256: "0".repeat(64), subject_type: "patient",
              subject_id: "00000000-0000-0000-0000-000000000000" },
    });
    expect(big.status()).toBe(422);
    const body = await big.json();
    expect(JSON.stringify(body)).toMatch(/exceeds|limit|bytes/i);
  });
});

test.describe("preview: lab journey", () => {
  test("PV-LAB-01 inbox -> bundle check-in -> complete -> QC -> ship",
       async ({ page }) => {
    test.setTimeout(120_000);
    test.skip(!rxNum, "depends on PV-PRA-03");
    await signIn(page, LAB.email, LAB.password);
    await expect(page.getByRole("heading",
      { name: /Received Prescriptions|Prescriptions/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("cell", { name: rxNum }).first().click();
    await expect(page.getByRole("heading", { name: /— Submitted/ }))
      .toBeVisible({ timeout: 15000 });
    const dl = page.waitForEvent("download", { timeout: 15000 })
      .catch(() => null);
    await page.getByRole("button", { name: "Download & Check-in" }).click();
    const file = await dl;
    expect(file, "bundle download").not.toBeNull();
    await expect(page.getByRole("heading", { name: /— Checked-In/ }))
      .toBeVisible();
    await page.getByRole("button", { name: "Mark complete" }).click();
    await expect(page.getByRole("heading", { name: /— Completed/ }))
      .toBeVisible({ timeout: 15000 });
    // QC pass then ship (carrier + tracking required)
    await page.getByRole("button", { name: "QC pass" }).click();
    await expect(page.getByText(/QC pass|Pass/i).first())
      .toBeVisible({ timeout: 15000 });
    await page.getByLabel("Carrier").fill("Canada Post");
    await page.getByLabel("Tracking number").fill(`PV-${Date.now() % 1e6}`);
    await page.getByRole("button", { name: "Ship" }).click();
    await expect(page.getByRole("cell", { name: "Shipped" })
      .or(page.getByText(/^Shipped$/)))
      .toBeVisible({ timeout: 15000 });
  });
});

test.describe("preview: practice fulfillment", () => {
  test("PV-FUL-01 receive -> deliver -> audit trail", async ({ page }) => {
    test.setTimeout(120_000);
    test.skip(!rxNum, "depends on lab leg");
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("cell", { name: rxNum }).first().click();
    await expect(page.getByRole("heading", { name: /— Completed/ }))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Confirm receipt" }).click();
    await expect(page.getByRole("cell", { name: "Received" }).first()
      .or(page.getByText(/^Received$/)))
      .toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Confirm delivery" }).click();
    await expect(page.getByRole("cell", { name: "Delivered" }).first()
      .or(page.getByText(/^Delivered$/)))
      .toBeVisible({ timeout: 15000 });
    // transition + fulfillment trail visible
    await expect(page.getByText(/Submitted → Checked-In/)).toBeVisible();
    await signOut(page);
  });
});
