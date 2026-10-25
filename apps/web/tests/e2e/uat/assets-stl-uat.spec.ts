/* UAT-ASSET-01..06 — STL & file handling on the web. */
import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { apiGet, apiLogin, LB_TECH, PA_ADMIN, signIn } from "./helpers";
import { ensureDataset } from "./dataset";
import { FIX, pwFile, uniqueStl } from "./fixtures";

let DS: Awaited<ReturnType<typeof ensureDataset>>;
test.beforeAll(async () => { DS = await ensureDataset(); });

async function openPatient(page: import("@playwright/test").Page,
                           ref: string) {
  await page.getByLabel("Search").fill(ref);
  // Wait for the debounced filter to land on the matching row — clicking
  // tbody tr.first() races the unfiltered list.
  const row = page.locator("tbody tr", { hasText: ref }).first();
  await expect(row).toBeVisible({ timeout: 10000 });
  await row.click();
  await expect(page.getByRole("heading",
    { name: "Treatment cases" })).toBeVisible({ timeout: 15000 });
}

test.describe("UAT-ASSET", () => {
  test("UAT-ASSET-01 upload upper+lower STL to a patient; bytes/sha/format shown",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openPatient(page, "UAT-P01");
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

    // both rows carry bytes + sha + format status
    for (const f of [FIX.upperBasic, FIX.lowerBasic]) {
      const row = page.locator("li", { hasText: f.sha256.slice(0, 16) });
      await expect(row).toContainText("valid mesh");
      await expect(row).toContainText(`${f.bytes} bytes`);
    }
  });

  test("UAT-ASSET-02 STL preview: orbit/zoom/reset produce real pixels",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openPatient(page, "UAT-P01");
    // need at least one uploaded STL (dedupe makes re-upload cheap)
    const previews = page.getByRole("button", { name: /^Preview/ });
    if ((await previews.count()) === 0) {
      await page.getByLabel("STL file").setInputFiles(pwFile(FIX.upperBasic));
      await page.getByLabel("Jaw").selectOption("upper");
      await page.getByRole("button", { name: "Upload STL" }).click();
      await expect(page.getByText(FIX.upperBasic.sha256.slice(0, 16)))
        .toBeVisible({ timeout: 30000 });
    }
    await previews.first().click();
    const canvas = page.locator("[aria-label=stl-preview] canvas").first();
    // Diagnostics for CI (software GL): if the canvas never mounts, report
    // the preview error and the GL renderer string instead of a bare timeout.
    if (!(await canvas.isVisible().catch(() => false))) {
      await page.waitForTimeout(3000);
      if (!(await canvas.isVisible())) {
        const alert = await page.getByRole("alert").allTextContents();
        const gl = await page.evaluate(() => {
          const c = document.createElement("canvas");
          const g = c.getContext("webgl");
          if (!g) return "NO_WEBGL_CONTEXT";
          const d = g.getExtension("WEBGL_debug_renderer_info");
          return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : "unknown";
        });
        throw new Error(
          `STL canvas never mounted. previewAlert=${JSON.stringify(alert)} webgl=${gl}`);
      }
    }
    await expect(canvas).toBeVisible({ timeout: 15000 });
    // The preview can sit below the fold: pointer events at off-viewport
    // coordinates never reach the canvas (elementFromPoint -> null), which
    // silently broke the orbit drag in CI. Scroll first, then measure.
    await canvas.scrollIntoViewIfNeeded();
    const box = (await canvas.boundingBox())!;
    // Read the real GL framebuffer (preserveDrawingBuffer is on) — immune
    // to compositor timing differences between GPU and software-WebGL CI.
    const shot = async () => await canvas.evaluate(
      (c) => (c as HTMLCanvasElement).toDataURL("image/png"));

    // WebGL repaints are async — poll until pixels actually change.
    const changed = async (prev: string) => {
      for (let i = 0; i < 20; i++) {
        await page.waitForTimeout(400);
        const cur = await shot();
        if (cur !== prev) return cur;
      }
      return null;
    };

    // First prove the mesh actually rendered: sample the framebuffer —
    // a blank canvas has exactly one colour, a rendered mesh does not.
    const distinctColors = async () => canvas.evaluate((c) => {
      const off = document.createElement("canvas");
      off.width = (c as HTMLCanvasElement).width;
      off.height = (c as HTMLCanvasElement).height;
      const ctx = off.getContext("2d")!;
      ctx.drawImage(c as HTMLCanvasElement, 0, 0);
      const d = ctx.getImageData(0, 0, off.width, off.height).data;
      const seen = new Set<number>();
      for (let i = 0; i < d.length; i += 397 * 4) {
        seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
      }
      return seen.size;
    });
    let s0 = "";
    for (let i = 0; i < 20 && (await distinctColors()) <= 1; i++) {
      await page.waitForTimeout(400);
      s0 = await shot();
    }
    expect(await distinctColors(),
      "mesh must render non-blank pixels").toBeGreaterThan(1);
    s0 = await shot();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 140, box.y + 40,
                          { steps: 10 });
    await page.mouse.up();
    const s1 = await changed(s0!);
    expect(s1, "orbit drag must change pixels").toBeTruthy();

    await page.mouse.wheel(0, -300);
    const s2 = await changed(s1!);
    expect(s2, "wheel zoom must change pixels").toBeTruthy();

    const reset = page.getByRole("button", { name: /reset/i });
    if (await reset.count()) {
      await reset.click();
      // Reset restores the camera; rendered pixels should differ from the
      // post-zoom frame (mesh returns to default framing).
      const s3 = await changed(s2!);
      expect(s3, "reset must restore the view").toBeTruthy();
    }
  });

  test("UAT-ASSET-03 patient STL download is non-empty and hash-verified",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openPatient(page, "UAT-P01");
    const row = page.locator("li",
      { hasText: FIX.upperBasic.sha256.slice(0, 16) }).first();
    await expect(row).toBeVisible({ timeout: 15000 });
    const dl = row.getByRole("button", { name: "Download" });
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 15000 }), dl.click()]);
    const path = await download.path();
    expect(path, "no download artifact").toBeTruthy();
    const buf = await import("node:fs").then((fs) =>
      fs.readFileSync(path!));
    expect(buf.length, "empty download").toBeGreaterThan(0);
    const sha = createHash("sha256").update(buf).digest("hex");
    // server returns raw object bytes -> sha must equal the fixture hash
    expect(sha).toBe(FIX.upperBasic.sha256);
  });

  test("UAT-ASSET-04 interrupted upload leaves no half-baked asset",
       async ({ page }) => {
    // browser-side: abort the complete call mid-flight — a run-unique
    // fixture keeps the sha out of the dedup path on re-runs.
    const file = uniqueStl("interrupt");
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openPatient(page, "UAT-P02");
    await page.route("**/v1/uploads/*/complete", (r) => r.abort());
    await page.getByLabel("STL file").setInputFiles(pwFile(file));
    await page.getByLabel("Jaw").selectOption("upper");
    await page.getByRole("button", { name: "Upload STL" }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 30000 });
    // the aborted asset must NOT appear as a completed file row
    const rows = await page.locator("li",
      { hasText: file.sha256.slice(0, 16) }).count();
    expect(rows, "aborted upload must not list an asset row").toBe(0);
    await page.unroute("**/v1/uploads/*/complete");
    // API-level proof: no completed asset exists for that sha
    const api = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
    const list = await (await apiGet(api,
      `/api/v1/patients/${DS.P02.id}/assets`)).json();
    expect(list.items.filter(
      (a: { asset: { sha256: string } }) =>
        a.asset.sha256 === file.sha256)).toHaveLength(0);
    await api.dispose();
  });

  test("UAT-ASSET-05 broken STL is rejected or never format_ok",
       async ({ page }) => {
    await signIn(page, PA_ADMIN.email, PA_ADMIN.password);
    await openPatient(page, "UAT-P02");
    await page.getByLabel("STL file").setInputFiles(pwFile(FIX.broken));
    await page.getByLabel("Jaw").selectOption("lower");
    await page.getByRole("button", { name: "Upload STL" }).click();
    await page.waitForTimeout(3000);
    // Either an error alert, or the row exists but is not format_ok and
    // offers no Preview button.
    const alert = await page.getByRole("alert").count();
    const row = page.locator("li",
      { hasText: FIX.broken.sha256.slice(0, 16) });
    if (alert === 0 && (await row.count()) > 0) {
      await expect(row).not.toContainText("valid mesh");
      await expect(row.getByRole("button", { name: /preview/i }))
        .toHaveCount(0);
    } else {
      expect(alert, "broken STL silently accepted").toBeGreaterThan(0);
    }
  });

  test("UAT-ASSET-06 unconnected lab cannot reach patient assets",
       async ({ page }) => {
    // LB (unconnected) — deep link to the patient is guarded
    await signIn(page, LB_TECH.email, LB_TECH.password);
    await page.goto(`/patients/${DS.P01.id}`);
    await expect(page.getByLabel("First name")).toHaveCount(0);
    // API-side double-check: LB cannot fetch the asset list
    const lb = await apiLogin(LB_TECH.email, LB_TECH.password);
    const r = await apiGet(lb, `/api/v1/patients/${DS.P01.id}/assets`);
    expect([401, 403]).toContain(r.status());
    await lb.dispose();
  });
});
