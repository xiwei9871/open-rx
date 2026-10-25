import { expect, test } from "@playwright/test";

// M3 fulfillment loop (E2E-10 backbone), synthetic data:
// submit -> check-in -> complete -> QC pass -> ship -> receive -> deliver
const PRACTICE = { email: "staff@pa.dev", password: "Passw0rd!dev" };
const LAB = { email: "tech@la.dev", password: "Passw0rd!dev" };

async function signIn(page: import("@playwright/test").Page,
                      email: string, password: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function selectByText(page: import("@playwright/test").Page,
                            label: string, text: string) {
  const sel = page.getByLabel(label);
  const value = await sel.locator("option", { hasText: text })
    .first().getAttribute("value");
  expect(value, `option "${text}" in ${label}`).toBeTruthy();
  await sel.selectOption(value!);
}

test("full delivery loop: qc -> ship -> receive -> deliver", async ({ page }) => {
  // practice: create + submit
  await signIn(page, PRACTICE.email, PRACTICE.password);
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await page.getByRole("button", { name: "New Rx" }).click();
  await selectByText(page, "Patient", "Synthetic, Ava");
  await selectByText(page, "Laboratory", "Friendly Lab");
  await selectByText(page, "catalog", "Adams clasp");
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("heading", { name: /— Saved/ })).toBeVisible();
  await page.getByLabel("Signature").fill("Dr. Demo");
  await page.getByRole("button", { name: "Sign & Submit" }).click();
  await expect(page.getByRole("heading", { name: /— Submitted/ })).toBeVisible();
  const rxNum = (await page.getByRole("heading", { level: 2 }).innerText())
    .split(" ")[0];

  // lab: check-in -> complete -> QC -> ship
  await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await signIn(page, LAB.email, LAB.password);
  await page.getByRole("cell", { name: rxNum }).click();
  await page.getByRole("button", { name: "Check in" }).click();
  await expect(page.getByRole("heading", { name: /— Checked-In/ })).toBeVisible();
  await page.getByRole("button", { name: "Mark complete" }).click();
  await expect(page.getByRole("heading", { name: /— Completed/ })).toBeVisible();
  await expect(page.getByTestId("fulfillment-status"))
    .toHaveText("qc_pending");
  await page.getByRole("button", { name: "QC pass" }).click();
  await expect(page.getByTestId("fulfillment-status"))
    .toHaveText("qc_passed");
  await page.getByLabel("Carrier").fill("UPS");
  await page.getByLabel("Tracking number").fill("1Z-E2E-SYNTH");
  await page.getByRole("button", { name: "Ship" }).click();
  await expect(page.getByTestId("fulfillment-status")).toHaveText("shipped");

  // practice: receive -> deliver
  await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await signIn(page, PRACTICE.email, PRACTICE.password);
  await page.getByRole("button", { name: "Prescriptions" }).click();
  await page.getByRole("cell", { name: rxNum }).click();
  await page.getByRole("button", { name: "Confirm receipt" }).click();
  await expect(page.getByTestId("fulfillment-status")).toHaveText("received");
  await page.getByRole("button", { name: "Confirm delivery" }).click();
  await expect(page.getByTestId("fulfillment-status")).toHaveText("delivered");
  // full logistics history present
  for (const ev of ["completed", "qc_pass", "shipped", "received",
                    "delivered"]) {
    await expect(page.getByTestId("fulfillment-events"))
      .toContainText(ev);
  }
});
