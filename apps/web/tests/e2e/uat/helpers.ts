/* Shared UAT helpers — synthetic data only. API calls are ONLY used to
 * establish preconditions; every asserted action happens in the browser. */
import { expect, request as pwRequest, type APIRequestContext,
         type Page } from "@playwright/test";

export const PA_ADMIN = { email: "admin@pa.dev", password: "Passw0rd!dev" };
export const PA_DOCTOR = { email: "doctor@pa.dev", password: "Passw0rd!dev" };
export const PA_STAFF = { email: "staff@pa.dev", password: "Passw0rd!dev" };
export const LA_ADMIN = { email: "admin@la.dev", password: "Passw0rd!dev" };
export const LA_TECH = { email: "tech@la.dev", password: "Passw0rd!dev" };
export const LB_TECH = { email: "lab2@lb.dev", password: "Passw0rd!dev" };

export const SIGN = "Dr. Demo";

export async function signIn(page: Page, email: string, password: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // Wait for the authenticated shell — a premature goto() can abort the
  // in-flight login POST and lose the Set-Cookie.
  await expect(page.getByRole("button", { name: "Sign out" }))
    .toBeVisible({ timeout: 15000 });
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
}

export async function selectByText(page: Page, label: string | RegExp,
                                   text: string | RegExp) {
  const sel = page.getByLabel(label);
  const opt = sel.locator("option", { hasText: text }).first();
  const value = await opt.getAttribute("value");
  expect(value, `option "${text}" under label "${label}"`).toBeTruthy();
  await sel.selectOption(value!);
}

/** Pick a patient on RxCreate — exercises the real filter input because
 * the picker no longer relies on the first page of patients. The select
 * is addressed by name to avoid colliding with the "Filter patients"
 * label (substring matching). */
export async function pickPatient(page: Page, name: string | RegExp) {
  const term = name instanceof RegExp ? name.source.replace(/[^A-Za-z ].*/g, "")
                                      : name;
  await page.locator("[name=patient_filter]").fill(term.trim());
  const sel = page.locator("select[name=patient]");
  const opt = sel.locator("option", { hasText: name }).first();
  const value = await opt.getAttribute("value");
  expect(value, `patient option "${name}"`).toBeTruthy();
  await sel.selectOption(value!);
}

/** API-side session for precondition setup only. */
export async function apiLogin(email: string, password: string):
    Promise<APIRequestContext> {
  const ctx = await pwRequest.newContext();
  const r = await ctx.post("/api/v1/auth/login", {
    data: { email, password },
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  expect(r.ok(), `apiLogin ${email}`).toBeTruthy();
  return ctx;
}

export async function apiPost(ctx: APIRequestContext, url: string,
                              body?: unknown, extraHeaders = {}) {
  const r = await ctx.post(url, {
    data: body ?? {},
    headers: { "X-Requested-With": "XMLHttpRequest",
               "Idempotency-Key": crypto.randomUUID(), ...extraHeaders },
  });
  return r;
}

export async function apiGet(ctx: APIRequestContext, url: string) {
  return ctx.get(url);
}

export async function apiPut(ctx: APIRequestContext, url: string,
                             body: unknown, extraHeaders = {}) {
  return ctx.put(url, {
    data: body,
    headers: { "X-Requested-With": "XMLHttpRequest",
               "Idempotency-Key": crypto.randomUUID(), ...extraHeaders },
  });
}

/** Upload an STL via the real presigned flow (setup only). */
export async function apiUploadStl(ctx: APIRequestContext,
                                   file: { name: string; buffer: Buffer;
                                           bytes: number; sha256: string },
                                   jaw = "upper") {
  const sess = await apiPost(ctx, "/api/v1/uploads", {
    sha256: file.sha256, bytes: file.bytes, kind: "stl", jaw,
    filename_hint: file.name,
  });
  expect(sess.ok(), "upload session").toBeTruthy();
  const s = await sess.json();
  const put = await ctx.fetch(s.upload_urls[0],
    { method: "PUT", data: file.buffer });
  expect(put.ok(), `PUT ${file.name}`).toBeTruthy();
  const done = await apiPost(ctx, `/api/v1/uploads/${s.id}/complete`,
    { sha256: file.sha256 });
  expect(done.ok(), `complete ${file.name}`).toBeTruthy();
  return done.json(); // Asset { id, ... }
}

export async function apiGrantPatient(ctx: APIRequestContext,
                                      assetId: string, patientId: string) {
  const r = await apiPost(ctx, `/api/v1/assets/${assetId}/references`, {
    subject_type: "patient", subject_id: patientId, role: "original",
  });
  expect(r.ok(), "grant patient ref").toBeTruthy();
}

export async function apiSubmitRx(ctx: APIRequestContext, rxId: string,
                                  signature = SIGN) {
  const cur = await (await apiGet(ctx, `/api/v1/rx/${rxId}`)).json();
  const r = await apiPost(ctx, `/api/v1/rx/${rxId}/submit`, {
    signature_name: signature, confirm_submit: true, note: null,
  }, { "If-Match": String(cur.version) });
  expect(r.ok(), `submit ${rxId}`).toBeTruthy();
}

export async function apiTransitions(ctx: APIRequestContext, rxId: string,
                                     steps: ("check-in" | "complete")[]) {
  for (const step of steps) {
    const cur = await (await apiGet(ctx, `/api/v1/rx/${rxId}`)).json();
    const r = await apiPost(ctx, `/api/v1/rx/${rxId}/${step}`, {},
                            { "If-Match": String(cur.version) });
    expect(r.ok(), `${step} ${rxId}`).toBeTruthy();
  }
}

export async function firstRxIdOnRow(page: Page): Promise<string | null> {
  // extract rx id from the current detail URL after clicking a row
  const m = page.url().match(/\/rx\/([0-9a-f-]{36})/);
  return m?.[1] ?? null;
}
