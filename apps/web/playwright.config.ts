import { defineConfig, devices } from "@playwright/test";

const localBaseUrl = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const localApiBaseUrl = new URL("/api/v1", localBaseUrl).toString().replace(/\/$/, "");
const listingOnly = process.argv.includes("--list");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "html",

  use: {
    baseURL: localBaseUrl,
    trace: "on-first-retry",
    launchOptions: process.env.PLAYWRIGHT_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH }
      : undefined,
  },

  webServer:
    process.env.E2E_USE_EXISTING_SERVER || listingOnly
      ? undefined
      : {
          command: "npm run dev",
          url: localBaseUrl,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            NEXT_PUBLIC_API_BASE_URL: localApiBaseUrl,
            NEXT_PUBLIC_API_TIMEOUT_MS: "10000",
          },
        },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
