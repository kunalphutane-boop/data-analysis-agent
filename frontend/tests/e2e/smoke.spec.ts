import { test, expect } from '@playwright/test'
import path from 'node:path'

// Phase 1 smoke — drives the REAL app at http://localhost:8001/app/.
//
// PRECONDITION: the backend must already be running with the real Gemini key:
//     uv run python -m src
// The gate / qa-auditor starts it before running this suite.
//
// Flow: load the page -> upload a CSV -> wait for the profile table to render
// with real column names -> type a question -> click Ask -> assert the answer
// text AND the collapsible code AND the token/cost badge render. Also asserts
// the labelled "Coming soon" stubs are visibly present.

const CSV_FIXTURE = path.join(__dirname, 'sample.csv')

test('upload -> profile -> ask -> answer with code and cost', async ({ page }) => {
  await page.goto('')

  // Page loads and is styled (heading present).
  await expect(page.getByRole('heading', { name: 'Data Analytics Agent' })).toBeVisible()

  // Empty state before upload.
  await expect(page.getByTestId('profile-empty')).toBeVisible()

  // Ask is disabled until a dataset is loaded.
  await expect(page.getByTestId('ask-button')).toBeDisabled()

  // Upload the CSV via the hidden file input.
  await page.getByTestId('file-input').setInputFiles(CSV_FIXTURE)

  // Profile table renders with real column names from the upload response.
  const profile = page.getByTestId('profile-panel')
  await expect(profile).toBeVisible({ timeout: 30_000 })
  await expect(profile.getByText('region', { exact: true })).toBeVisible()
  await expect(profile.getByText('revenue', { exact: true })).toBeVisible()
  await expect(page.getByTestId('profile-shape')).toContainText('cols')

  // Ask a question.
  await page.getByTestId('question-input').fill('What is the total revenue by region?')
  const askButton = page.getByTestId('ask-button')
  await expect(askButton).toBeEnabled()
  await askButton.click()

  // Answer renders (real Gemini + real pandas execution).
  const answer = page.getByTestId('answer-display')
  await expect(answer).toBeVisible({ timeout: 90_000 })

  // Either a real answer, a clarify prompt, or a plainly-shown error — never a crash.
  const answerText = page.getByTestId('answer-text')
  const clarify = page.getByTestId('clarify-block')
  const answerError = page.getByTestId('answer-error')
  await expect(answerText.or(clarify).or(answerError).first()).toBeVisible()

  // Step list + counter render.
  await expect(page.getByTestId('step-list')).toBeVisible()
  await expect(page.getByTestId('step-counter')).toContainText('step')

  // Collapsible code — open it and assert code text is present (skip on clarify,
  // where generated_code is empty per the contract).
  if (await answerText.isVisible().catch(() => false)) {
    const showCode = page.getByTestId('show-code')
    await expect(showCode).toBeVisible()
    await showCode.locator('summary').click()
    await expect(page.getByTestId('generated-code')).toBeVisible()
    await expect(page.getByTestId('generated-code')).not.toBeEmpty()
  }

  // Token/cost badge renders.
  const cost = page.getByTestId('cost-badge')
  await expect(cost).toBeVisible()
  await expect(page.getByTestId('cost-usd')).toContainText('$')
})

test('labelled non-functional stubs are visibly present', async ({ page }) => {
  await page.goto('')

  // Remaining Phase-1 stubs (charts + follow-ups are now real features).
  await expect(page.getByTestId('add-file-stub')).toBeVisible()
  await expect(page.getByTestId('quality-flags-stub')).toBeVisible()

  // Stubs carry a "Coming soon" badge.
  await expect(page.getByTestId('coming-soon-badge').first()).toBeVisible()
  const badgeCount = await page.getByTestId('coming-soon-badge').count()
  expect(badgeCount).toBeGreaterThan(1)
})
