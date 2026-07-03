import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Phase 4 E2E — Conversation Intelligence, driven against the REAL app at
// http://localhost:8001/app/.
//
// PRECONDITION: the backend must already be running with the real Gemini key:
//     uv run python -m src
// The gate / qa-auditor starts it before running this suite.
//
// Flow: load the page -> upload a transcript CSV (with a "Conversation Log"
// column) -> wait for the profile -> click "Analyze conversations" -> confirm the
// column picker defaults to "Conversation Log" -> Start -> watch the progress bar
// -> on completion assert the Intent breakdown, Outcome breakdown, and cross-tab
// table render and the Download labelled CSV button is present.
//
// The classify job runs real Gemini over every row, so allow generous time.

// Prefer the backend's synthetic fixture if present (created by the backend
// slice); otherwise fall back to a self-contained transcript CSV in this dir.
function transcriptFixture(): string {
  const backendFixture = path.join(
    __dirname,
    '..',
    '..',
    '..',
    'tests',
    'fixtures',
    'transcripts_synthetic.csv',
  )
  if (fs.existsSync(backendFixture)) return backendFixture
  return path.join(__dirname, 'transcripts.csv')
}

test('analyze conversations -> progress -> breakdowns + cross-tab + download', async ({
  page,
}) => {
  test.setTimeout(300_000) // real Gemini classification over every row

  await page.goto('')
  await expect(page.getByRole('heading', { name: 'Data Analytics Agent' })).toBeVisible()

  // Upload the transcript CSV via the hidden file input.
  await page.getByTestId('file-input').setInputFiles(transcriptFixture())

  // Profile renders with the transcript column.
  const profile = page.getByTestId('profile-panel')
  await expect(profile).toBeVisible({ timeout: 60_000 })
  await expect(profile.getByText('Conversation Log', { exact: true })).toBeVisible()

  // The Conversation Intelligence section is shown on the loaded dataset.
  const ci = page.getByTestId('conversation-intelligence')
  await expect(ci).toBeVisible()

  // Reveal the picker.
  await page.getByTestId('analyze-conversations').click()

  // Business Context panel is present with its helper text. Author + save a lending
  // context so the run is grounded in the user's domain.
  const bcPanel = page.getByTestId('business-context-panel')
  await expect(bcPanel).toBeVisible()
  await expect(page.getByTestId('business-context-helper')).toBeVisible()
  const bcInput = page.getByTestId('business-context-input')
  await bcInput.fill(
    'We are a lending NBFC; this call center handles loan servicing, EMI, ' +
      'KYC/verification, disbursement and collections.',
  )
  await page.getByTestId('business-context-save').click()
  // After a changed save, the "re-run to re-classify" notice appears.
  await expect(page.getByTestId('business-context-saved')).toBeVisible({ timeout: 15_000 })

  // The column picker defaults to "Conversation Log".
  const select = page.getByTestId('transcript-column-select')
  await expect(select).toBeVisible()
  await expect(select).toHaveValue('Conversation Log')

  // Start the job.
  await page.getByTestId('classify-start').click()

  // Progress bar appears (may complete quickly for a small file).
  const progress = page.getByTestId('classify-progress')
  const results = page.getByTestId('classify-results')
  await expect(progress.or(results).first()).toBeVisible({ timeout: 30_000 })

  // Wait for the results panel (job done). Never crashes — either results or a
  // plainly-shown error.
  const errorBlock = page.getByTestId('classify-error')
  await expect(results.or(errorBlock).first()).toBeVisible({ timeout: 280_000 })

  // Assert real results rendered (not the error path).
  await expect(results).toBeVisible()

  // Intent breakdown table.
  await expect(page.getByTestId('intent-breakdown')).toBeVisible()
  await expect(page.getByTestId('intent-rows').locator('tr').first()).toBeVisible()

  // Per-intent summary: expand the first intent that has a summary toggle and read it.
  const summaryToggle = page.getByTestId('intent-summary-toggle').first()
  await expect(summaryToggle).toBeVisible()
  await summaryToggle.click()
  const summaryText = page.getByTestId('intent-summary-text').first()
  await expect(summaryText).toBeVisible()
  await expect(summaryText).not.toBeEmpty()

  // Outcome breakdown — Positive / Neutral / Negative rows. Scope to the table
  // rows (the outcome chart below also renders these labels).
  const outcome = page.getByTestId('outcome-breakdown')
  await expect(outcome).toBeVisible()
  const outcomeRows = page.getByTestId('outcome-rows')
  await expect(outcomeRows.getByText('Positive', { exact: true })).toBeVisible()
  await expect(outcomeRows.getByText('Neutral', { exact: true })).toBeVisible()
  await expect(outcomeRows.getByText('Negative', { exact: true })).toBeVisible()

  // Cross-tab table with a header row.
  const crossTab = page.getByTestId('cross-tab')
  await expect(crossTab).toBeVisible()
  await expect(crossTab.getByText('Total', { exact: true })).toBeVisible()
  await expect(page.getByTestId('cross-tab-rows').locator('tr').first()).toBeVisible()

  // A chart accompanies each analysis (intent, outcome, cross-tab).
  await expect(page.getByTestId('intent-chart')).toBeVisible()
  await expect(page.getByTestId('outcome-chart')).toBeVisible()
  await expect(page.getByTestId('cross-tab-chart')).toBeVisible()

  // Repeat-calls analysis. The fixture has a `call_id` column, so real stats +
  // the distribution chart render (not the "no call identifier" note).
  const repeat = page.getByTestId('repeat-calls')
  await expect(repeat).toBeVisible()
  await expect(page.getByTestId('repeat-unique-callers')).toBeVisible()
  await expect(page.getByTestId('repeat-distribution-chart')).toBeVisible()

  // Download labelled CSV button is present and points at the labelled.csv endpoint.
  const download = page.getByTestId('download-labelled-csv')
  await expect(download).toBeVisible()
  await expect(download).toHaveAttribute('href', /\/classify\/jobs\/.+\/labelled\.csv$/)
})

test('conversation intelligence action is present on a loaded dataset', async ({ page }) => {
  await page.goto('')
  await page.getByTestId('file-input').setInputFiles(transcriptFixture())
  await expect(page.getByTestId('profile-panel')).toBeVisible({ timeout: 60_000 })

  // The action is shown; charts + sessions sidebar remain stubbed.
  await expect(page.getByTestId('analyze-conversations')).toBeVisible()
  await expect(page.getByTestId('sessions-sidebar')).toBeVisible()
})
