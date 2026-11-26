import { expect, test, type Page } from "@playwright/test";

const API = "http://localhost:8000/api/v1";
const SHOTS = "../docs/screenshots";
type J = any;

async function call(path: string, token?: string, body?: unknown): Promise<J> {
  const r = await fetch(API + path, { method: body ? "POST" : "GET", headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  return r.json();
}
const token = async (email: string) => (await call("/auth/login", undefined, { email, password: "Demo@1234" })).access_token as string;

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Demo@1234");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
}

test("full rescue: donor posts, NGO claims in UI, volunteer completes pickup and delivery in UI", async ({ page }) => {
  test.setTimeout(120_000);
  const donorTok = await token("donor3@demo.com");
  const cooked = new Date(Date.now() - 15 * 60000).toISOString();
  const listing = await call("/listings", donorTok, { title: "E2E full flow dal rice", food_category: "cooked_meal", storage_condition: "hot_holding", is_veg: true, quantity_meals: 30, cooked_at: cooked });
  expect(listing.id, JSON.stringify(listing)).toBeTruthy();

  // find the NGO that was notified
  let ngoEmail = "";
  for (let i = 1; i <= 9 && !ngoEmail; i++) {
    const t = await token(`ngo${i}@demo.com`);
    const items = (await call("/listings?status=open&limit=200", t)).items ?? [];
    if (items.some((x: J) => x.id === listing.id)) ngoEmail = `ngo${i}@demo.com`;
  }
  expect(ngoEmail, "no NGO was notified").not.toBe("");

  // NGO claims through the UI
  await login(page, ngoEmail);
  await page.getByText("E2E full flow dal rice").first().waitFor();
  await page.getByRole("button", { name: "Claim", exact: true }).first().click();
  await expect(page.getByRole("tab", { name: /My pickups/ })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/40-ngo-after-claim.png`, fullPage: true });
  await page.getByRole("button", { name: "Log out" }).click();

  // find the volunteer who was offered the pickup
  let volEmail = "", pickupId = 0, volTok = "";
  for (let i = 1; i <= 10 && !volEmail; i++) {
    const t = await token(`volunteer${i}@demo.com`);
    const p = ((await call("/pickups/mine", t)).items ?? []).find((x: J) => x.listing.id === listing.id);
    if (p) { volEmail = `volunteer${i}@demo.com`; pickupId = p.id; volTok = t; }
  }
  expect(volEmail, "no volunteer offered").not.toBe("");

  await login(page, volEmail);
  await page.getByRole("button", { name: "Accept job" }).click();
  await page.getByRole("button", { name: /Start trip/ }).click();
  const pickupOtp = ((await call("/pickups/mine", donorTok)).items.find((x: J) => x.id === pickupId)).pickup_otp;
  expect(pickupOtp).toMatch(/^\d{4}$/);

  // wrong code first: must show an error, not crash
  await page.getByLabel("OTP code").fill(pickupOtp === "0000" ? "1111" : "0000");
  for (const t of ["Food is covered", "Container is clean", "Temperature looks right"]) await page.getByLabel(new RegExp(t)).check();
  await page.getByRole("button", { name: "Confirm pickup" }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();

  await page.getByLabel("OTP code").fill(pickupOtp);
  await page.getByRole("button", { name: "Confirm pickup" }).click();
  await expect(page.getByText("Ask the NGO for the 4-digit delivery code")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/41-volunteer-picked-up.png`, fullPage: true });

  const ngoTok = await token(ngoEmail);
  const deliveryOtp = ((await call("/pickups/mine", ngoTok)).items.find((x: J) => x.id === pickupId)).delivery_otp;
  await page.getByLabel("OTP code").fill(deliveryOtp);
  await page.getByRole("button", { name: "Confirm delivery" }).click();
  await expect(page.getByText("Delivered").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/42-volunteer-delivered.png`, fullPage: true });

  const final = await call(`/listings/${listing.id}`, donorTok);
  expect(final.status).toBe("delivered");
});
