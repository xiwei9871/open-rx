#!/usr/bin/env node
/* Virtual-clinic UAT aggregator.
 *
 * 1. Runs the UAT Playwright suite (tests/e2e/uat/*.spec.ts) with the JSON
 *    reporter.
 * 2. Writes a machine-readable summary + human-readable results to
 *    docs/audit/evidence/virtual-clinic/.
 * 3. Captures key-page screenshots (clinic + lab roles, desktop + mobile)
 *    as committed evidence.
 *
 * Usage (from apps/web):
 *   node tests/e2e/uat/run-clinic-audit.mjs           # full suite + shots
 *   node tests/e2e/uat/run-clinic-audit.mjs --shots   # screenshots only
 *
 * Requires the dev stack on E2E_BASE_URL (default http://localhost:5173).
 */
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(HERE, "../../..");
const REPO = resolve(WEB, "../..");
const OUT = resolve(REPO, "docs/audit/evidence/virtual-clinic");
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const shotsOnly = process.argv.includes("--shots");

mkdirSync(OUT, { recursive: true });

if (!shotsOnly) {
  console.log(`[clinic-audit] running UAT suite against ${BASE}`);
  const jsonPath = resolve(OUT, "results.json");
  let out = "";
  let code = 0;
  try {
    out = execFileSync("npx", ["playwright", "test", "tests/e2e/uat/",
      "--reporter=json"], {
      cwd: WEB, encoding: "utf8",
      stdio: ["ignore", "pipe", "inherit"], maxBuffer: 64 * 1024 * 1024,
    }).toString();
  } catch (e) {
    code = e.status ?? 1;
    out = e.stdout?.toString() ?? "";
  }
  // strip the "Running N tests..." preamble line from stdout
  const report = JSON.parse(out.slice(out.indexOf("{")));
  writeFileSync(jsonPath, JSON.stringify(report));
  const rows = report.suites.flatMap((f) => f.suites.flatMap((d) =>
    d.specs.map((s) => ({
      id: s.title.match(/UAT-[A-Z]+-?\d*/)?.[0] ?? s.title,
      title: s.title,
      file: f.file,
      ok: s.ok === true,
      duration_ms: s.tests.reduce((a, t) =>
        a + t.results.reduce((b, r) => b + r.duration, 0), 0),
    }))));
  const summary = {
    base_url: BASE,
    generated_at: new Date().toISOString(),
    total: rows.length,
    passed: rows.filter((r) => r.ok).length,
    failed: rows.filter((r) => !r.ok).length,
    cases: rows,
  };
  writeFileSync(resolve(OUT, "summary.json"),
    JSON.stringify(summary, null, 2));
  writeFileSync(resolve(OUT, "summary.csv"),
    "uat_id,title,file,ok,duration_ms\n" + rows.map((r) =>
      `${r.id},"${r.title.replaceAll('"', '""')}",${r.file},${r.ok},${r.duration_ms}`
    ).join("\n") + "\n");
  console.log(`[clinic-audit] ${summary.passed}/${summary.total} passed` +
    ` -> ${resolve(OUT, "summary.json")}`);
  if (code !== 0) {
    console.log("[clinic-audit] suite had failures; capturing evidence anyway");
  }
}

// ---- key-page screenshots ---------------------------------------------
const PA = { email: "admin@pa.dev", password: "Passw0rd!dev" };
const LA = { email: "admin@la.dev", password: "Passw0rd!dev" };

const browser = await chromium.launch();
async function shot(page, name) {
  await page.screenshot({ path: resolve(OUT, `${name}.png`),
    fullPage: false });
  console.log(`[clinic-audit] shot ${name}.png`);
}
async function login(page, u) {
  await page.goto("/");
  await page.getByLabel("Email").fill(u.email);
  await page.getByLabel("Password").fill(u.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Sign out" }).waitFor({ timeout: 15000 });
}

const desk = await browser.newContext({ baseURL: BASE,
  viewport: { width: 1440, height: 900 } });
let page = await desk.newPage();
await page.goto("/");
await shot(page, "01-login");
await login(page, PA);
await shot(page, "02-patient-list");
await page.getByLabel(/search/i).fill("UAT-P01").catch(() => {});
await page.waitForTimeout(600);
const row = page.locator("tbody tr", { hasText: "UAT-P01" }).first();
if (await row.count()) {
  await row.click();
  await shot(page, "03-patient-detail");
}
await page.getByRole("button", { name: "Prescriptions" }).click();
await shot(page, "04-rx-list");
await page.getByRole("button", { name: "New Rx" }).click();
await page.waitForTimeout(800);
await shot(page, "05-rx-create");
await page.getByRole("button", { name: "Prescriptions" }).click();
await page.waitForTimeout(800);
const rxRow = page.locator("tbody tr", { hasText: /RX\d+/ }).first();
if (await rxRow.count()) {
  await rxRow.locator("td").first().click();
  await page.waitForTimeout(800);
  await shot(page, "06-rx-detail");
}
await page.getByRole("button", { name: "Inbox" }).click()
  .catch(() => {});
await page.waitForTimeout(600);
await shot(page, "07-practice-inbox");
await desk.close();

const lab = await browser.newContext({ baseURL: BASE,
  viewport: { width: 1440, height: 900 } });
page = await lab.newPage();
await login(page, LA);
await shot(page, "10-lab-inbox");
const labRow = page.locator("tbody tr", { hasText: /RX\d+/ }).first();
if (await labRow.count()) {
  await labRow.locator("td").first().click();
  await page.waitForTimeout(800);
  await shot(page, "11-lab-rx-detail");
}
await lab.close();

const mob = await browser.newContext({ baseURL: BASE,
  viewport: { width: 390, height: 844 } });
page = await mob.newPage();
await login(page, PA);
await shot(page, "20-mobile-patients");
await page.getByRole("button", { name: "Prescriptions" }).click();
await shot(page, "21-mobile-rx-list");
await mob.close();
await browser.close();
console.log(`[clinic-audit] screenshots -> ${OUT}`);
