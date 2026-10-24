import { expect, test } from "@playwright/test";

// S1b-Core browser loop, synthetic data only:
// practice: create -> items -> sign & submit
// lab: inbox -> check-in
// practice: unsubmit is rejected once checked in.
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

test.describe("rx core loop", () => {
  test("create -> submit -> lab check-in -> unsubmit rejected", async ({ page }) => {
    // practice side
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("button", { name: "New Rx" }).click();

    await selectByText(page, "Patient", "Synthetic, Ava");
    await selectByText(page, "Laboratory", "Friendly Lab");
    await selectByText(page, "Doctor", "Dr\. Demo");
    await page.getByLabel("Due date").fill("2030-01-15");
    await selectByText(page, "catalog", "Hawley retainer");
    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.getByText(/HWL — Hawley retainer \(upper\)/)).toBeVisible();
    await page.getByRole("button", { name: "Save draft" }).click();

    await expect(page.getByRole("heading", { name: /RX\d+ — Saved/ })).toBeVisible();
    await page.getByLabel("Signature").fill("Dr. Demo");
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ })).toBeVisible();
    const rxNum = (await page.getByRole("heading", { level: 2 }).innerText())
      .split(" ")[0];

    // lab side: inbox -> check-in
    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, LAB.email, LAB.password);
    await expect(
      page.getByRole("heading", { name: "Received Prescriptions" })).toBeVisible();
    await page.getByRole("cell", { name: rxNum }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ })).toBeVisible();
    await page.getByRole("button", { name: "Check in" }).click();
    await expect(page.getByRole("heading", { name: /— Checked-In/ })).toBeVisible();
    await expect(page.getByText(/submitted → checked_in/)).toBeVisible();

    // practice side: unsubmit is rejected with a clear message
    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("cell", { name: rxNum }).click();
    await expect(page.getByRole("heading", { name: /— Checked-In/ })).toBeVisible();
    await page.getByRole("button", { name: "Unsubmit" }).click();
    await expect(page.getByRole("alert")).toContainText(/checked in/i);
    await expect(page.getByRole("heading", { name: /— Checked-In/ })).toBeVisible();
  });

  test("unsubmit before check-in returns to Saved", async ({ page }) => {
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("button", { name: "New Rx" }).click();
    await selectByText(page, "Patient", "Synthetic, Ava");
    await selectByText(page, "Laboratory", "Friendly Lab");
    await selectByText(page, "catalog", "Adams clasp");
    await page.getByRole("button", { name: "Add" }).click();
    await page.getByRole("button", { name: "Save draft" }).click();
    await page.getByRole("button", { name: "Sign & Submit" }).click();
    await expect(page.getByRole("heading", { name: /— Submitted/ })).toBeVisible();
    await page.getByRole("button", { name: "Unsubmit" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ })).toBeVisible();
    // editable again: save notes
    await page.getByLabel("Notes").fill("re-edited after unsubmit");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Saved");
  });
});
