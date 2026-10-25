import { expect, test, type Page } from "@playwright/test";

const ADMIN = { email: "admin@pa.dev", password: "Passw0rd!dev" };
const LAB = { email: "admin@la.dev", password: "Passw0rd!dev" };

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator(".appbar")).toBeVisible();
}

async function selectOption(page: Page, name: string, text: string) {
  const sel = page.locator(`select[name=${name}]`);
  const value = await sel.locator("option", { hasText: text })
    .first().getAttribute("value");
  await sel.selectOption(value!);
}

test("deep link: refresh on rx detail keeps context and URL", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByRole("button", { name: "Prescriptions" }).click();
  const row = page.locator("table.data tbody tr").first();
  await expect(row).toContainText(/RX\d+/);
  await row.click();
  await expect(page.getByRole("heading", { name: /RX\d+ — / })).toBeVisible();
  const url = page.url();
  expect(url).toMatch(/\/rx\/[0-9a-f-]{36}/);
  await page.reload();
  // session restored and detail context survives the reload
  await expect(page.getByRole("heading", { name: /RX\d+ — / })).toBeVisible();
  expect(page.url()).toBe(url);
});

test("browser back/forward walks history", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await expect(page).toHaveURL(/\/rx$/);
  const firstRow = page.locator("table.data tbody tr").first();
  await expect(firstRow).toContainText(/RX\d+/);
  await firstRow.click();
  await expect(page).toHaveURL(/\/rx\/[0-9a-f-]{36}/);
  await page.goBack();
  await expect(page).toHaveURL(/\/rx$/);
  await page.goForward();
  await expect(page.getByRole("heading", { name: /RX\d+ — / }))
    .toBeVisible();
});

test("required catalog options use inline fields, not dialogs", async ({ page }) => {
  let nativeDialog = false;
  page.on("dialog", (d) => { nativeDialog = true; void d.dismiss(); });
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await page.getByRole("button", { name: "New Rx" }).click();
  const bndValue = await page
    .locator("select[name=catalog] option", { hasText: /BND/ })
    .first().getAttribute("value");
  await page.locator("select[name=catalog]").selectOption(bndValue!);
  // required option field appears inline; Add is blocked until filled
  const opt = page.getByLabel("Option band_tooth");
  await expect(opt).toBeVisible();
  await page.getByRole("button", { name: "Add item" }).click();
  await expect(page.getByRole("alert"))
    .toContainText(/required.*band_tooth/i);
  await opt.fill("16");
  await page.getByRole("button", { name: "Add item" }).click();
  await expect(page.getByText(/BND.*band_tooth=16/)).toBeVisible();
  expect(nativeDialog).toBe(false);
});

test("rx list and detail show names, not raw ids", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByRole("button", { name: "Prescriptions" }).click();
  const firstRow = page.locator("table.data tbody tr").first();
  await expect(firstRow).toContainText(/P\d{6}|Synthetic/);
  await firstRow.click();
  await expect(page.getByRole("row", { name: /Patient/ })
    .or(page.locator("table.kv tr", { hasText: "Patient" })))
    .toContainText(/P\d{6} —/);
  await expect(page.locator("table.kv")).not.toContainText(/[0-9a-f]{8}-[0-9a-f]{4}/);
});

test("lab sees patient label on received rx detail", async ({ page }) => {
  await signIn(page, LAB.email, LAB.password);
  const row = page.locator("table.data tbody tr").first();
  await expect(row).toContainText(/RX\d+/);
  await row.click();
  await expect(page.locator("table.kv"))
    .toContainText(/P\d{6} —/);
});

test("mobile 390px: no horizontal overflow, nav usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await expect(page.locator("table.data")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth -
          document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
