import { defineConfig } from "@playwright/test";

// E2E_BROWSER_CHANNEL=chrome uses the locally installed Chrome (avoids the
// ~130MB browser download on slow links); CI installs bundled chromium.
export default defineConfig({
  testDir: "tests/e2e",
  globalSetup: "tests/e2e/global-setup.ts",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    channel: process.env.E2E_BROWSER_CHANNEL || undefined,
    // CI runners have no GPU: Chromium >=129 refuses software WebGL
    // (SwiftShader) unless explicitly enabled — without this the STL
    // preview can never create a GL context there. Harmless on machines
    // with real GPUs.
    launchOptions: { args: ["--enable-unsafe-swiftshader"] },
  },
});
