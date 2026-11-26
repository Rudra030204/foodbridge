import { defineConfig } from "@playwright/test";

/** Needs the backend running and freshly seeded on :8000 (see README). Vite is started automatically. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  expect: { timeout: 15_000 },
  use: { launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}, baseURL: "http://localhost:5173", screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: { command: "npm run dev", url: "http://localhost:5173", reuseExistingServer: true, timeout: 60_000 },
});
