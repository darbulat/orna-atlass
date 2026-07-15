import { defineConfig, devices } from "@playwright/test";

const mockApiUrl = "http://127.0.0.1:4010";
const apiUrl = process.env.E2E_API_URL ?? mockApiUrl;
const nextServer = {
  command: `API_SERVER_URL=${apiUrl} NEXT_PUBLIC_API_URL=${apiUrl} NEXT_DIST_DIR=.next-codex-e2e npm run dev -- --hostname 127.0.0.1 --port 3100`,
  url: "http://127.0.0.1:3100",
  reuseExistingServer: !process.env.CI,
  timeout: 120_000,
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "on-first-retry",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.E2E_API_URL
    ? nextServer
    : [
        {
          command: "node e2e/mock-api.mjs",
          url: `${mockApiUrl}/health`,
          reuseExistingServer: !process.env.CI,
          timeout: 30_000,
        },
        nextServer,
      ],
});
