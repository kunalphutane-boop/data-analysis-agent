import { defineConfig, devices } from '@playwright/test'

// Phase 1 smoke config.
//
// This suite drives the REAL app against a live backend. The backend must
// already be running with the real Gemini key from `.env`:
//
//     uv run python -m src          # serves the app + API at :8001/app/
//
// The gate / qa-auditor starts that server before running `pnpm exec
// playwright test`. We intentionally do NOT start a webServer here because the
// static export is served by FastAPI, not by Next, and the tests exercise the
// real /ask path (real Gemini, real pandas execution).
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000, // real Gemini + pandas execution can take a while
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:8001/app/',
    trace: 'on-first-retry',
    actionTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
