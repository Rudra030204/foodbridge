import { expect, test, type Page } from "@playwright/test";

const SHOTS = "../docs/screenshots";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Demo@1234");
  await page.getByRole("button", { name: "Log in" }).click();
}

test("landing page shows live counters", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Meals rescued")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/01-landing.png`, fullPage: true });
});

test("donor posts surplus, sees countdown and match explanation", async ({ page }) => {
  await login(page, "donor1@demo.com");
  await expect(page).toHaveURL(/\/donor$/);
  await page.getByRole("link", { name: /Post surplus food/ }).first().click();

  // client-side validation blocks an empty submit
  await page.getByRole("button", { name: /Post and notify/ }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();

  await page.getByLabel("What is it?").fill("E2E veg biryani");
  await page.getByLabel("Quantity (meals)").fill("40");
  await expect(page.getByTestId("safety-preview").getByTestId("countdown")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/02-post-form.png`, fullPage: true });
  await page.getByRole("button", { name: /Post and notify/ }).click();

  await expect(page).toHaveURL(/\/donor\/listings\/\d+$/);
  await expect(page.getByRole("heading", { name: "E2E veg biryani" })).toBeVisible();
  await expect(page.getByTestId("countdown").first()).toBeVisible();
  await expect(page.getByText("Why these NGOs?")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/03-listing-detail.png`, fullPage: true });
});

test("role guard: a volunteer cannot open the admin page", async ({ page }) => {
  await login(page, "volunteer1@demo.com");
  await expect(page).toHaveURL(/\/volunteer$/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/volunteer$/);
  await page.screenshot({ path: `${SHOTS}/04-volunteer.png`, fullPage: true });
});

test("ngo sees offers; admin sees verification queue", async ({ page }) => {
  await login(page, "ngo1@demo.com");
  await expect(page.getByRole("tab", { name: /Offers/ })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/05-ngo.png`, fullPage: true });
  await page.getByRole("button", { name: "Log out" }).click();

  await login(page, "admin@demo.com");
  await expect(page.getByRole("heading", { name: "Admin console" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/06-admin.png`, fullPage: true });
});
