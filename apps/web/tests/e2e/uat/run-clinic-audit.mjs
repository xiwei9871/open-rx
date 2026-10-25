#!/usr/bin/env node
/* Virtual-clinic UAT aggregator — hard-gated.

 * 1. Runs the UAT Playwright suite (tests/e2e/uat/*.spec.ts) with the JSON
 *    reporter and retain-on-failure traces.
 * 2. Writes results.json + summary.json/csv + key-page screenshots to
 *    docs/audit/evidence/virtual-clinic/ — ALWAYS, pass or fail.
 * 3. Summary carries an explicit verdict: PASS or FAIL.
 * 4. Completeness: every expected UAT-ID must have executed; a spec file
 *    that failed to load or a skipped case counts as FAIL (never silently
 *    treated as green).
 * 5. Exit code: 0 only when all expected cases ran and passed, otherwise
 *    non-zero AFTER evidence is saved.
 *
 * Failure injection (proves the gate is real):
 *   node tests/e2e/uat/run-clinic-audit.mjs --inject-failure
 *   -> skips running the suite, emits a synthetic failing summary, and
 *   must exit 1. `run-clinic-audit.mjs --self-test` asserts that.
 *
 * Usage (from apps/web):
 *   node tests/e2e/uat/run-clinic-audit.mjs
 *   node tests/e2e/uat/run-clinic-audit.mjs --shots      # screenshots only
 *   node tests/e2e/uat/run-clinic-audit.mjs --self-test  # injection check
 */
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(HERE, "../../..");
const REPO = resolve(WEB, "../..");
const OUT = resolve(REPO, "docs/audit/evidence/virtual-clinic");
const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";

const shotsOnly = process.argv.includes("--shots");
const selfTest = process.argv.includes("--self-test");
if (selfTest) {
  // Prove the gate is real: the injection run must exit non-zero.
  try {
    execFileSync(process.execPath,
      [fileURLToPath(import.meta.url), "--inject-failure"],
      { stdio: ["ignore", "pipe", "pipe"], maxBuffer: 16 * 1024 * 1024 });
    console.log("[clinic-audit] self-test FAILED: injection exited 0");
    process.exit(1);
  } catch (e) {
    const s = e.status ?? 1;
    if (s !== 1) {
      console.log(`[clinic-audit] self-test FAILED: injection exit=${s}`);
      process.exit(1);
    }
    console.log("[clinic-audit] self-test PASS: injection exited 1");
    process.exit(0);
  }
}
const injectFailure = process.argv.includes("--inject-failure");

// The contract: every UAT case that must execute. Titles like
// "UAT-FULFILL-01..04" run as a single Playwright case, so the expected
// list matches what the suite actually produces (49 cases).
const EXPECTED = [
  ...[1, 2, 3, 4].map((n) => `UAT-AUTH-0${n}`),
  ...[1, 2, 3, 4, 5].map((n) => `UAT-PAT-0${n}`),
  ...[1, 2, 3, 4, 5, 6].map((n) => `UAT-ASSET-0${n}`),
  ...[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => `UAT-RX-${String(n).padStart(2, "0")}`),
  ...[1, 2, 3, 4, 5, 6].map((n) => `UAT-LAB-0${n}`),
  ...[1, 2, 3, 4, 5].map((n) => `UAT-COLLAB-0${n}`),
  "UAT-FULFILL-01", "UAT-FULFILL-05",
  ...[1, 2, 3, 4, 5].map((n) => `UAT-NEG-0${n}`),
  ...[1, 2, 3, 4, 5].map((n) => `UAT-E-0${n}`),
  "UAT-JOURNEY",
];

mkdirSync(OUT, { recursive: true });

function extractId(specTitle, suiteTitle) {
  return specTitle.match(/UAT-[A-Z]+-?\d*/)?.[0]
      ?? suiteTitle.match(/UAT-[A-Z]+-?\d*/)?.[0]
      ?? specTitle;
}

let rows = [];
let suiteError = null;

if (injectFailure) {
  rows = EXPECTED.map((id) => ({
    id, title: `${id} (injected)`, file: "-", ok: id !== "UAT-AUTH-01",
    duration_ms: 0 }));
  suiteError = "injected-failure";
} else if (!shotsOnly) {
  console.log(`[clinic-audit] running UAT suite against ${BASE}`);
  let out = "";
  try {
    out = execFileSync("npx", [
      "playwright", "test", "tests/e2e/uat/",
      "--reporter=json", "--trace", "retain-on-failure",
    ], { cwd: WEB, encoding: "utf8",
         stdio: ["ignore", "pipe", "inherit"],
         maxBuffer: 64 * 1024 * 1024 }).toString();
  } catch (e) {
    out = e.stdout?.toString() ?? "";
    suiteError = `playwright exited ${e.status ?? "unknown"}`;
  }
  try {
    const report = JSON.parse(out.slice(out.indexOf("{")));
    writeFileSync(resolve(OUT, "results.json"), JSON.stringify(report));
    for (const f of report.suites) {
      for (const d of f.suites) {
        for (const s of d.specs) {
          const ran = s.tests.length > 0
            && s.tests.every((t) => t.results.length > 0);
          rows.push({
            id: extractId(s.title, d.title),
            title: `${d.title} › ${s.title}`,
            file: f.file,
            ok: s.ok === true && ran,
            ran,
            duration_ms: s.tests.reduce((a, t) =>
              a + t.results.reduce((b, r) => b + r.duration, 0), 0),
          });
        }
      }
    }
  } catch {
    suiteError = suiteError ?? "playwright produced no JSON report";
  }
}

if (!shotsOnly) {
  const executed = new Set(rows.map((r) => r.id));
  const missing = EXPECTED.filter((id) => !executed.has(id));
  const failed = rows.filter((r) => !r.ok).map((r) => r.id);
  const verdict = (suiteError || missing.length || failed.length)
    ? "FAIL" : "PASS";
  const summary = {
    base_url: BASE,
    generated_at: new Date().toISOString(),
    verdict,
    expected: EXPECTED.length,
    executed: rows.length,
    passed: rows.filter((r) => r.ok).length,
    failed_ids: failed,
    missing_ids: missing,
    suite_error: suiteError,
    cases: rows,
  };
  writeFileSync(resolve(OUT, "summary.json"), JSON.stringify(summary, null, 2));
  writeFileSync(resolve(OUT, "summary.csv"),
    "uat_id,title,file,ok,duration_ms\n" + rows.map((r) =>
      `${r.id},"${r.title.replaceAll('"', '""')}",${r.file},${r.ok},${r.duration_ms}`
    ).join("\n") + "\n");
  console.log(`[clinic-audit] verdict=${verdict} ` +
    `${summary.passed}/${summary.expected} passed` +
    (missing.length ? ` missing=[${missing}]` : "") +
    (failed.length ? ` failed=[${failed}]` : "") +
    (suiteError ? ` suite_error=${suiteError}` : ""));
}

// ---- key-page screenshots (always captured on real runs) ---------------
if (!injectFailure) {
const PA = { email: "admin@pa.dev", password: "Passw0rd!dev" };
const LA = { email: "admin@la.dev", password: "Passw0rd!dev" };

const browser = await chromium.launch();
async function shot(page, name) {
  await page.screenshot({ path: resolve(OUT, `${name}.png`) });
  console.log(`[clinic-audit] shot ${name}.png`);
}
async function login(page, u) {
  await page.goto("/");
  await page.getByLabel("Email").fill(u.email);
  await page.getByLabel("Password").fill(u.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Sign out" }).waitFor({ timeout: 15000 });
}

try {
  const desk = await browser.newContext({ baseURL: BASE,
    viewport: { width: 1440, height: 900 } });
  let page = await desk.newPage();
  await page.goto("/");
  await shot(page, "01-login");
  await login(page, PA);
  await shot(page, "02-patient-list");
  await page.locator("input[aria-label=Search], input[name=patient_filter]")
    .first().fill("UAT-P01").catch(() => {});
  await page.waitForTimeout(600);
  const prow = page.locator("tbody tr", { hasText: "UAT-P01" }).first();
  if (await prow.count()) {
    await prow.click();
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
  await page.getByRole("button", { name: "Inbox" }).click().catch(() => {});
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
} finally {
  await browser.close();
}
console.log(`[clinic-audit] screenshots -> ${OUT}`);
}

// ---- exit contract -----------------------------------------------------
if (injectFailure) process.exit(1);
if (shotsOnly) process.exit(0);

const summary = JSON.parse(
  readFileSync(resolve(OUT, "summary.json"), "utf8"));
process.exit(summary.verdict === "PASS" ? 0 : 1);
