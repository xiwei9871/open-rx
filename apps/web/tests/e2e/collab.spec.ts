import { expect, test } from "@playwright/test";

// M2 collaboration loop, synthetic data only:
// practice submits Rx -> lab raises approval-required issue ->
// practice approves in Inbox -> lab completes -> lab sends ack ->
// practice reads it.
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

test.describe("m2 collaboration", () => {
  test("approval request -> decision -> lab complete -> ack", async ({ page }) => {
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

    // lab: check in, request approval, comment, complete
    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, LAB.email, LAB.password);
    await page.getByRole("cell", { name: rxNum }).click();
    await page.getByRole("button", { name: "Check in" }).click();
    await expect(page.getByRole("heading", { name: /— Checked-In/ })).toBeVisible();

    await page.getByLabel("Issue kind").selectOption("approval_required");
    await page.getByLabel("Issue subject").fill("Approve shortened retention");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByRole("status")).toContainText("inbox");

    // practice: inbox shows the pending approval, approve with signature.
    // (must precede lab Complete — completion bumps rx.version, which would
    // correctly stale the request: 409 version_drift.)
    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await page.getByRole("button", { name: "Inbox" }).click();
    // inbox is newest-first; repeated runs may leave older resolved copies
    const card = page.getByTestId("notification")
      .filter({ hasText: "Approve shortened retention" })
      .filter({ has: page.getByLabel(/^signature /) }).first();
    await expect(card).toBeVisible();
    await card.getByLabel(/^signature /).fill("Dr. Demo");
    await card.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByTestId("notification")
      .filter({ hasText: "Approve shortened retention" })
      .filter({ hasText: "resolved" }).first()).toBeVisible();

    // lab: complete the order
    await page.getByRole("button", { name: "Sign out" }).click();
    await signIn(page, LAB.email, LAB.password);
    await page.getByRole("cell", { name: rxNum }).click();
    await page.getByRole("button", { name: "Mark complete" }).click();
    await expect(page.getByRole("heading", { name: /— Completed/ })).toBeVisible();
    await expect(page.getByText(/checked_in → completed/)).toBeVisible();
  });

  test("comments + attachment discussion on an Rx", async ({ page }) => {
    await signIn(page, PRACTICE.email, PRACTICE.password);
    await page.getByRole("button", { name: "Prescriptions" }).click();
    await page.getByRole("button", { name: "New Rx" }).click();
    await selectByText(page, "Patient", "Synthetic, Ava");
    await selectByText(page, "Laboratory", "Friendly Lab");
    await selectByText(page, "catalog", "Adams clasp");
    await page.getByRole("button", { name: "Add" }).click();
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("heading", { name: /— Saved/ })).toBeVisible();
    await page.getByPlaceholder("Add comment").fill("Please verify pontic site");
    await page.getByRole("button", { name: "Post" }).click();
    await expect(page.getByText("Please verify pontic site")).toBeVisible();
  });
});
