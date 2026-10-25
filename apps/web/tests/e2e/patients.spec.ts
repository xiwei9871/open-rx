import { expect, test } from "@playwright/test";

// Synthetic data only — exercises the real stack end to end:
// nginx -> api -> postgres RLS -> presigned PUT -> rustfs -> complete.
const ADMIN = { email: "admin@pa.dev", password: "Passw0rd!dev" };

const STL = `solid probe
facet normal 0 0 0
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid probe
`;

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
}

test.describe("patient workbench", () => {
  test("seeded patient searchable and opens detail with case", async ({ page }) => {
    await signIn(page);
    await page.getByLabel("Search").fill("SYN-0001");
    await page.getByRole("button", { name: "Search" }).click();
    await page.getByRole("cell", { name: "Synthetic, Ava" }).click();
    await expect(page.getByRole("heading", { name: /Synthetic, Ava/ })).toBeVisible();
    await expect(page.getByText("Initial alignment (synthetic)")).toBeVisible();
  });

  test("create -> edit -> case -> STL upload -> file listed", async ({ page }) => {
    await signIn(page);
    const tag = Date.now().toString(36);
    await page.getByLabel("First name").fill("E2E");
    await page.getByLabel("Last name").fill(`Browser${tag}`);
    await page.getByLabel("Date of birth").fill("2012-02-02");
    await page.getByRole("button", { name: "Create patient" }).click();

    await expect(page.getByRole("heading", { name: new RegExp(`Browser${tag}, E2E`) }))
      .toBeVisible();
    await page.getByLabel("Notes").fill("created by playwright");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toContainText("Saved");

    await page.getByLabel("Case label").fill(`Aligner ${tag}`);
    await page.getByRole("button", { name: "Open case" }).click();
    await expect(page.getByText(`Aligner ${tag}`)).toBeVisible();

    await page.getByLabel("STL file").setInputFiles({
      name: "probe.stl", mimeType: "model/stl", buffer: Buffer.from(STL),
    });
    await page.getByLabel("Jaw").selectOption("upper");
    await page.getByRole("button", { name: "Upload STL" }).click();
    await expect(page.getByText(/sha256 [0-9a-f]{16}/)).toBeVisible({ timeout: 15000 });
  });

  test("duplicate name+dob prompts confirmation", async ({ page }) => {
    await signIn(page);
    const tag = `Dup${Date.now().toString(36)}`;
    for (const first of ["AA", "BB"]) {
      await page.getByLabel("First name").fill(first);
      await page.getByLabel("Last name").fill(tag);
      await page.getByLabel("Date of birth").fill("2001-01-01");
      await page.getByRole("button", { name: "Create patient" }).click();
      if (first === "AA") {
        // navigates to detail — go back to list
        await page.getByRole("button", { name: "Patients" }).click();
      } else {
        await expect(page.getByText("Possible duplicate patients")).toBeVisible();
        await page.getByRole("button", { name: "Create anyway" }).click();
        await expect(page.getByRole("heading", { name: new RegExp(`${tag}, BB`) }))
          .toBeVisible();
      }
    }
  });
});
