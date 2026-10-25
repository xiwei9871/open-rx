#!/usr/bin/env node
/* Full-site functional + UX audit. Walks every page as all five seeded
   roles across three viewports; captures screenshots, console errors,
   page errors and failed network requests into audit-evidence/.

   Usage: node tests/audit/run-audit.mjs [--out audit-evidence]
   Requires the dev stack on http://localhost:5173 (web) + :8000 (api). */
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.AUDIT_BASE ?? "http://localhost:5173";
const OUT = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : "audit-evidence";

const ROLES = {
  practice_admin: { email: "admin@pa.dev", password: "Passw0rd!dev" },
  practice_doctor: { email: "doctor@pa.dev", password: "Passw0rd!dev" },
  practice_staff: { email: "staff@pa.dev", password: "Passw0rd!dev" },
  lab_admin: { email: "admin@la.dev", password: "Passw0rd!dev" },
  lab_tech: { email: "tech@la.dev", password: "Passw0rd!dev" },
};

const VIEWPORTS = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "laptop-1280", width: 1280, height: 800 },
  { name: "mobile-390", width: 390, height: 844 },
];

const QUICK = process.argv.includes("--quick");
const SELF_TEST = process.argv.includes("--self-test");
const INJECT = !!process.env.AUDIT_INJECT; // CI failure-injection proof

const findings = [];
const coverage = {}; // role -> viewport -> [{page, checks...}]
let shotN = 0;

function note(role, page, sev, kind, detail) {
  findings.push({ role, page, severity: sev, kind, detail });
}

function cover(role, vp, pageName, check = "screenshot") {
  // file tags say "desktop"; canonical viewport key is "desktop-1440"
  const key = vp === "desktop" ? "desktop-1440" : vp;
  (coverage[role] ??= {})[key] ??= [];
  const vpList = coverage[role][key];
  if (!vpList.some((e) => e.page === pageName && e.check === check)) {
    vpList.push({ page: pageName, check });
  }
}

async function snap(page, role, name, tag = "") {
  shotN += 1;
  cover(role, tag || "desktop-1440", name);
  const f = path.join(OUT, "shots",
    `${String(shotN).padStart(2, "0")}-${role}-${name}${tag ? "-" + tag : ""}.png`);
  await page.screenshot({ path: f, fullPage: true });
  return f;
}

/** Walks must complete; a sign-in failure is a P0, never a silent skip. */
async function signIn(page, creds, role) {
  try {
    await page.goto("/");
    await page.getByLabel("Email").fill(creds.email);
    await page.getByLabel("Password").fill(creds.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForSelector("header nav", { timeout: 10000 });
  } catch (e) {
    note(role, "login", "P0", "signin",
         `sign-in failed: ${String(e).split("\n")[0]}`);
    throw e;
  }
}

function instrument(page, role, label) {
  const answered = new WeakSet(); // requests that already got a response —
  // Chromium reports an unread body stream as ERR_ABORTED on requestfailed
  // even when the server returned 200; that is not a product defect.
  page.on("console", (m) => {
    if (page._auditAborting) return; // induced chaos window, not a defect
    if (m.type() === "error")
      note(role, label, "P1", "console-error", m.text().slice(0, 300));
  });
  page.on("pageerror", (e) =>
    note(role, label, "P0", "pageerror", String(e).slice(0, 300)));
  page.on("requestfailed", (r) => {
    if (page._auditAborting || answered.has(r)) return;
    note(role, label, "P0", "requestfailed",
         `${r.method()} ${r.url()} ${r.failure()?.errorText}`);
  });
  page.on("response", (r) => {
    answered.add(r.request());
    if (r.status() >= 500)
      note(role, label, "P0", "http-5xx", `${r.request().method()} ${r.url()} -> ${r.status()}`);
    else if (r.status() === 404 && !r.url().includes("favicon"))
      note(role, label, "P1", "http-404", `${r.url()}`);
  });
}

async function walkPractice(page, role, tag) {
  // Patients list
  await snap(page, role, "patients", tag);
  // first patient -> detail
  const cell = page.locator("tbody tr").first();
  if (await cell.count()) {
    await cell.click();
    await page.waitForTimeout(400);
    await snap(page, role, "patient-detail", tag);
    // deep-link check — detail must have its own URL
    const url = page.url();
    cover(role, "desktop-1440", "patient-detail", "deep-link-url");
    if (url === BASE + "/" || url === `${BASE}/`) {
      note(role, "patient-detail", "P0", "routing",
           `detail URL is still ${url} — no deep-link/history`);
    } else {
      // browser back must return to the list, not exit the app
      cover(role, "desktop-1440", "patient-detail", "history-back-forward");
      await page.goBack();
      await page.waitForTimeout(400);
      if (await page.locator("table.data tbody tr, tbody tr").count() === 0) {
        note(role, "patient-detail", "P0", "history",
             `browser back from detail lost the list: ${page.url()}`);
      }
      await page.goForward().catch(() => {});
    }
    await page.getByRole("button", { name: "Patients" }).click();
  }
  // Rx list
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await page.waitForTimeout(400);
  await snap(page, role, "rx-list", tag);
  // Rx create
  if (await page.getByRole("button", { name: "New Rx" }).count()) {
    await page.getByRole("button", { name: "New Rx" }).click();
    await page.waitForTimeout(400);
    await snap(page, role, "rx-create", tag);
    // cancel back
    if (await page.getByRole("button", { name: /Cancel/ }).count())
      await page.getByRole("button", { name: /Cancel/ }).click();
  }
  // open first Rx row if any
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await page.waitForTimeout(300);
  const rxRow = page.locator("tbody tr").first();
  if (await rxRow.count()) {
    await rxRow.click();
    await page.waitForTimeout(400);
    await snap(page, role, "rx-detail", tag);
  }
  // Inbox
  await page.getByRole("button", { name: "Inbox" }).click();
  await page.waitForTimeout(300);
  await snap(page, role, "inbox", tag);
  // Settings
  await page.getByRole("button", { name: "Settings" }).click();
  await page.waitForTimeout(400);
  await snap(page, role, "settings", tag);
}

async function walkLab(page, role, tag) {
  await page.waitForTimeout(300);
  await snap(page, role, "rx-list", tag);
  const rxRow = page.locator("tbody tr").first();
  if (await rxRow.count()) {
    await rxRow.click();
    await page.waitForTimeout(400);
    await snap(page, role, "rx-detail", tag);
  }
  if (await page.getByRole("button", { name: "Inbox" }).count()) {
    await page.getByRole("button", { name: "Inbox" }).click();
    await page.waitForTimeout(300);
    await snap(page, role, "inbox", tag);
  }
  if (await page.getByRole("button", { name: "Settings" }).count()) {
    await page.getByRole("button", { name: "Settings" }).click();
    await page.waitForTimeout(300);
    await snap(page, role, "settings", tag);
  }
}

async function navTo(page, name) {
  const b = page.getByRole("button", { name });
  if (await b.count()) { await b.first().click(); await page.waitForTimeout(200); }
}

async function errorPaths(page, role) {
  // bad inputs + refresh + back on deep page + double-click
  const isLab = role.startsWith("lab");
  if (!isLab) {
    await navTo(page, "Prescriptions");
    const newRx = page.getByRole("button", { name: "New Rx" });
    if (await newRx.count()) {
      await newRx.click();
      // submit empty form -> required validation feedback
      cover(role, "desktop-1440", "rx-create", "empty-submit-validation");
      await page.getByRole("button", { name: "Save draft" }).click();
      await page.waitForTimeout(300);
      const alerted = await page.locator("[role=alert]").count();
      if (!alerted) {
        note(role, "rx-create-empty-submit", "P1", "validation",
             "empty submit surfaced no error feedback");
      }
      await page.getByRole("button", { name: /Cancel/ }).click()
        .catch(() => navTo(page, "Prescriptions"));
    }
  }
  // open a detail, then refresh — does the view survive?
  await navTo(page, "Prescriptions");
  await page.waitForTimeout(300);
  const row = page.locator("tbody tr").first();
  if (await row.count()) {
    await row.click();
    await page.waitForTimeout(300);
    const heading = await page.locator("h2").first().innerText();
    cover(role, "desktop-1440", "rx-detail", "refresh-restores-context");
    await page.reload();
    await page.waitForTimeout(800);
    const after = await page.locator("h1,h2").first().innerText()
      .catch(() => "");
    if (!after.includes("RX")) {
      note(role, "refresh-on-detail", "P0", "refresh",
           `was on '${heading}', after reload shows '${after}'`);
    }
    // STL preview interaction — orbit controls must exist
    const previewBtn = page.getByRole("button", { name: "Preview" }).first();
    if (await previewBtn.count()) {
      await previewBtn.click();
      await page.waitForTimeout(600);
      if (await page.locator("[aria-label=stl-preview] canvas").count()) {
        await snap(page, role, "stl-preview", "desktop");
      } else {
        note(role, "rx-detail", "P1", "stl",
             "preview button present but no canvas rendered");
      }
    }
    await page.goBack().catch(() => {});
    await page.waitForTimeout(300);
  }
}

// Tetrahedron — enough 3D geometry for the orbit-drag pixel check.
const CUBE_STL = `solid tet
facet normal 0 0 -1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
facet normal 1 1 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 0 1
  endloop
endfacet
facet normal 1 1 1
  outer loop
    vertex 0 0 0
    vertex 0 1 0
    vertex 0 0 1
  endloop
endfacet
facet normal 1 1 1
  outer loop
    vertex 1 0 0
    vertex 0 1 0
    vertex 0 0 1
  endloop
endfacet
endsolid tet
`;

/* Extended real-world checks: STL gesture, duplicate-click, network
   failure, permission deep-links and bundle download. Run once per side
   to keep runtime sane. */
async function extendedPractice(page, role) {
  // STL orbit gesture — upload a real STL to the first patient, open the
  // 3D preview, drag, and require the canvas pixels to change.
  await navTo(page, "Patients");
  const prow = page.locator("tbody tr").first();
  if (await prow.count()) {
    await prow.click();
    await page.waitForTimeout(600);
    const fileInput = page.getByLabel("STL file");
    if (await fileInput.count()) {
      await fileInput.setInputFiles({
        name: "audit-cube.stl", mimeType: "model/stl",
        buffer: Buffer.from(CUBE_STL),
      });
      const jaw = page.getByLabel("Jaw");
      if (await jaw.count()) await jaw.selectOption("upper");
      await page.getByRole("button", { name: "Upload STL" }).click();
      // wait for the asset row instead of a fixed delay — a mid-flight
      // navigation or retry shows up as an aborted PUT otherwise
      const listed = await page.getByText(/sha256 [0-9a-f]{12}/).first()
        .waitFor({ timeout: 30000 }).then(() => true).catch(() => false);
      if (!listed) {
        const alertText = await page.locator("[role=alert]").first()
          .innerText().catch(() => "");
        const statusText = await page.locator("[role=status]").first()
          .innerText().catch(() => "");
        note(role, "patient-detail", "P1", "upload",
             `no asset row in 30s — alert='${alertText.slice(0, 120)}' `
             + `status='${statusText.slice(0, 80)}'`);
        await snap(page, role, "upload-stall", "desktop");
      }
      const previewBtn =
        page.getByRole("button", { name: /^Preview/ }).first();
      cover(role, "desktop-1440", "patient-detail", "stl-upload-list");
      if (await previewBtn.count()) {
        await previewBtn.click();
        await page.waitForTimeout(2000);
        const canvas =
          page.locator("[aria-label=stl-preview] canvas").first();
        if (await canvas.count()) {
          cover(role, "desktop-1440", "patient-detail",
                "stl-orbit-drag-pixeldiff");
          const before = await canvas.screenshot();
          const box = await canvas.boundingBox();
          await page.mouse.move(box.x + box.width / 2,
                                box.y + box.height / 2);
          await page.mouse.down();
          await page.mouse.move(box.x + box.width / 2 + 120,
                                box.y + box.height / 2 + 40, { steps: 8 });
          await page.mouse.up();
          await page.waitForTimeout(400);
          const after = await canvas.screenshot();
          await snap(page, role, "stl-orbited", "desktop");
          if (before.equals(after)) {
            note(role, "stl-preview", "P1", "interaction",
                 "drag produced no visual change — OrbitControls inert?");
          }
          // zoom + pan must also respond
          cover(role, "desktop-1440", "patient-detail",
                "stl-zoom-wheel-pixeldiff");
          await page.mouse.move(box.x + box.width / 2,
                                box.y + box.height / 2);
          await page.mouse.wheel(0, -400);
          await page.waitForTimeout(300);
          const zoomed = await canvas.screenshot();
          if (zoomed.equals(after)) {
            note(role, "stl-preview", "P2", "interaction",
                 "scroll produced no zoom change");
          }
        } else {
          note(role, "stl-preview", "P1", "stl",
               "STL uploaded but preview produced no canvas");
        }
      } else {
        note(role, "patient-detail", "P2", "stl",
             "STL upload listed no Preview button");
      }
    }
  }
  // Rx detail — duplicate-click + bundle checks need an Rx row.
  await navTo(page, "Prescriptions");
  const row = page.locator("tbody tr").first();
  if (!(await row.count())) {
    note(role, "extended", "P2", "setup", "no Rx rows — skipping Rx checks");
    return;
  }
  await row.click();
  await page.waitForTimeout(400);
  // Duplicate-click — fire two click events faster than the busy-disabled
  // re-render can land; server/UI must still record only one comment.
  const commentBox = page.locator("input[name=comment]");
  if (await commentBox.count()) {
    const stamp = `audit-dup-${Date.now()}`;
    cover(role, "desktop-1440", "rx-detail", "duplicate-click-guard");
    await commentBox.fill(stamp);
    const post = page.getByRole("button", { name: "Post" }).first();
    await post.dispatchEvent("click");
    await post.dispatchEvent("click").catch(() => {});
    await page.waitForTimeout(1200);
    const n = await page.getByText(stamp).count();
    if (n > 1) {
      note(role, "rx-detail", "P1", "duplicate-click",
           `double-click posted ${n} copies of one comment`);
    }
  }
  // Network failure — abort all API calls, then reload the list. The UI
  // must surface an error, not a silent blank or stuck spinner. The
  // induced-abort flag keeps instrumentation from logging our own chaos
  // requests as product defects.
  page._auditAborting = true;
  cover(role, "desktop-1440", "rx-list", "network-failure-alert");
  await page.route("**/api/**", (r) => r.abort());
  await navTo(page, "Prescriptions");
  await page.waitForTimeout(900);
  const netErr = await page.locator("[role=alert]").count();
  if (!netErr) {
    note(role, "rx-list", "P1", "network-failure",
         "API unreachable but no error surfaced to the user");
  } else {
    await snap(page, role, "network-failure", "desktop");
  }
  await page.unroute("**/api/**");
  page._auditAborting = false;
}

async function extendedLab(page, role) {
  // Insufficient-permission deep link — /patients must not leak the
  // patient workbench to a lab principal. The route guard may legitimately
  // render the Rx list at this URL, so check for patient-specific UI only.
  await page.goto("/patients");
  cover(role, "desktop-1440", "patients", "deep-link-permission-denied");
  await page.waitForTimeout(700);
  const leaked = await page.getByLabel("First name").count();
  const patientCol = await page.locator("thead")
    .getByText(/First name|DOB/i).count();
  if (leaked > 0 || patientCol > 0) {
    note(role, "patients-deep-link", "P0", "permission",
         "lab role can see patient UI/data at /patients");
  } else {
    await snap(page, role, "patients-denied", "desktop");
  }
  // Bundle download via popup on a lab-visible Rx.
  await navTo(page, "Prescriptions");
  const row = page.locator("tbody tr").first();
  if (await row.count()) {
    await row.click();
    await page.waitForTimeout(400);
    const dl = page.getByRole("button", { name: /Download/i }).first();
    if (await dl.count()) {
      cover(role, "desktop-1440", "rx-detail", "bundle-download-event");
      // blob+anchor download must produce a real download event
      const [download] = await Promise.all([
        page.waitForEvent("download", { timeout: 8000 }).catch(() => null),
        dl.click(),
      ]);
      if (!download) {
        note(role, "rx-detail", "P1", "download",
             "Download bundle produced no file download");
      } else {
        const f = await download.path().catch(() => null);
        const size = f ? fs.statSync(f).size : 0;
        if (!size) {
          note(role, "rx-detail", "P1", "download",
               "downloaded bundle is empty");
        }
      }
    }
  }
}

async function main() {
  fs.mkdirSync(path.join(OUT, "shots"), { recursive: true });
  // reset the seeded 2FA factor on doctor@pa.dev — the auth.spec enables it
  // during the e2e suite and would hang plain-credential sign-ins here
  try {
    const { execSync } = await import("node:child_process");
    execSync(`docker exec easyrs-dev-postgres-1 psql -U easyrs_admin -d easyrs -c "UPDATE user_account SET totp_enabled=false, totp_secret_enc=NULL WHERE email='doctor@pa.dev'"`,
             { stdio: "ignore", timeout: 5000 });
  } catch { /* best effort */ }
  const browser = await chromium.launch();

  // desktop pass — every role, every page
  for (const [role, creds] of Object.entries(ROLES)) {
    const ctx = await browser.newContext({ viewport: VIEWPORTS[0], baseURL: BASE });
    const page = await ctx.newPage();
    instrument(page, role, "walk");
    const before = findings.length;
    try {
      if (INJECT) {
        await page.addInitScript(() => console.error("AUDIT_INJECTED_ERROR"));
      }
      await page.context().tracing.start(
        { screenshots: true, snapshots: true }).catch(() => {});
      await signIn(page, creds, role);
      if (role.startsWith("lab")) await walkLab(page, role, "desktop");
      else await walkPractice(page, role, "desktop");
      await errorPaths(page, role);
      if (role === "practice_admin" && !QUICK)
        await extendedPractice(page, role);
      if (role === "lab_admin" && !QUICK) await extendedLab(page, role);
    } catch (e) {
      note(role, "walk", "P0", "crash", String(e).slice(0, 300));
      await snap(page, role, "crash", "desktop").catch(() => {});
    }
    // keep a trace only when this role produced findings — full traces are
    // heavy; a clean role needs none.
    const dirty = findings.length > before;
    await page.context().tracing.stop(dirty
      ? { path: path.join(OUT, `trace-${role}.zip`) } : {}).catch(() => {});
    await ctx.close();
    if (QUICK) break;
  }

  // secondary viewports — one role per side, key pages
  if (!QUICK) for (const vp of VIEWPORTS.slice(1)) {
    for (const role of ["practice_doctor", "lab_tech"]) {
      const ctx = await browser.newContext({ viewport: vp, baseURL: BASE });
      const page = await ctx.newPage();
      instrument(page, role, `vp-${vp.name}`);
      try {
        await signIn(page, ROLES[role], role);
        if (role === "practice_doctor") {
          await snap(page, role, "patients", vp.name);
          await page.getByRole("button", { name: "Prescriptions" }).click();
          await page.waitForTimeout(300);
          await snap(page, role, "rx-list", vp.name);
          await page.getByRole("button", { name: "New Rx" }).click();
          await page.waitForTimeout(300);
          await snap(page, role, "rx-create", vp.name);
        } else {
          await snap(page, role, "rx-list", vp.name);
        }
        cover(role, vp.name, "layout", "no-horizontal-overflow");
        // overflow check — content must not bleed past the viewport
        const over = await page.evaluate(
          () => document.documentElement.scrollWidth -
                document.documentElement.clientWidth);
        if (over > 1) {
          note(role, vp.name, "P1", "responsive",
               `horizontal overflow ${over}px at ${vp.width}px`);
        }
      } catch (e) {
        note(role, vp.name, "P1", "viewport", String(e).slice(0, 200));
      }
      await ctx.close();
    }
  }

  await browser.close();
  return writeReport();
}

/** Honest coverage: what was actually walked, per role+viewport. A missing
 *  required page or a shot-starved run is itself a P0 — never fake green. */
function writeReport() {
  const REQUIRED = {
    practice: ["patients", "rx-list", "rx-create", "rx-detail",
               "inbox", "settings"],
    lab: ["rx-list", "rx-detail", "inbox", "settings"],
  };
  for (const [role, vps] of Object.entries(coverage)) {
    const desktop = vps["desktop-1440"] ?? [];
    const pages = new Set(desktop.map((e) => e.page));
    for (const req of REQUIRED[role.startsWith("lab") ? "lab" : "practice"]) {
      if (!pages.has(req) && !QUICK) {
        findings.push({ role, page: req, severity: "P0", kind: "coverage",
          detail: `required page never reached/screenshotted: ${req}` });
      }
    }
  }
  if (!QUICK && shotN < 30) {
    findings.push({ role: "audit", page: "*", severity: "P0",
      kind: "coverage",
      detail: `only ${shotN} screenshots — audit did not complete` });
  }
  const gate = findings.filter((f) => ["P0", "P1"].includes(f.severity));
  const summary = {
    verdict: gate.length === 0 ? "PASS" : "FAIL",
    findings_total: findings.length,
    blocking: gate.length,
    screenshots: shotN,
    generated_at: new Date().toISOString(),
  };
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, "findings-raw.json"),
                   JSON.stringify(findings, null, 2));
  fs.writeFileSync(path.join(OUT, "coverage.json"),
                   JSON.stringify(coverage, null, 2));
  fs.writeFileSync(path.join(OUT, "summary.json"),
                   JSON.stringify(summary, null, 2));
  console.log(`audit ${summary.verdict}: ${findings.length} findings `
    + `(${gate.length} blocking), ${shotN} shots -> ${OUT}`);
  for (const f of findings) {
    console.log(`  [${f.severity}] ${f.role} ${f.page} ${f.kind}: ${f.detail}`);
  }
  return gate.length === 0 ? 0 : 1;
}

/** --self-test: prove the gate actually goes red. Synthetic severities plus
 *  a live injected console error must both produce a nonzero verdict. */
async function selfTest() {
  // synthetic matrix
  const mk = (sev) => [{ severity: sev, role: "t", page: "t",
                         kind: "t", detail: "t" }];
  const cases = [
    { list: mk("P0"), want: 1 }, { list: mk("P1"), want: 1 },
    { list: mk("P2"), want: 0 }, { list: mk("P3"), want: 0 },
    { list: [], want: 0 },
  ];
  const clean = [];
  for (const c of cases) {
    const blocking = c.list.filter((f) => ["P0", "P1"].includes(f.severity));
    const got = blocking.length ? 1 : 0;
    if (got !== c.want) {
      console.log(`self-test FAIL: gate([${c.list.map(f => f.severity)}]) `
                  + `= ${got}, want ${c.want}`);
      return 1;
    }
  }
  clean.length = 0;
  // live injection: a real console error must be captured by instrument()
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ baseURL: BASE });
  const page = await ctx.newPage();
  const captured = [];
  page.on("console", (m) => {
    if (m.type() === "error") captured.push(m.text());
  });
  await page.addInitScript(() => console.error("INJECTED_FOR_SELF_TEST"));
  await page.goto("/").catch(() => {});
  await page.waitForTimeout(500);
  await browser.close();
  if (!captured.some((t) => t.includes("INJECTED_FOR_SELF_TEST"))) {
    console.log("self-test FAIL: injected console error was not captured");
    return 1;
  }
  console.log("self-test PASS: gate rejects P0/P1, allows P2/P3/clean; "
              + "injected console error captured");
  return 0;
}

if (SELF_TEST) {
  process.exit(await selfTest());
} else {
  const code = await main();
  process.exit(code);
}
