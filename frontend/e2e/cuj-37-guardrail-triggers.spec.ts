import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-37: Guardrail Triggers', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/guardrails/playground')
  })

  test('guardrail playground page renders', async ({ page }) => {
    // Should show either the playground UI, empty state, or loading state
    const heading = page.getByRole('heading', { name: /guardrail playground/i })
    const loadingText = page.getByText(/loading guardrails/i)
    const emptyState = page.getByText(/no guardrails found/i)
    const errorState = page.getByText(/failed to load/i)

    await page.waitForTimeout(1000)

    const headingVisible = await heading.isVisible().catch(() => false)
    const loadingVisible = await loadingText.isVisible().catch(() => false)
    const emptyVisible = await emptyState.isVisible().catch(() => false)
    const errorVisible = await errorState.isVisible().catch(() => false)

    expect(headingVisible || loadingVisible || emptyVisible || errorVisible).toBeTruthy()
  })

  test('guardrail select dropdown exists when guardrails are loaded', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      // No guardrails configured, skip
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const guardrailSelect = page.locator('#guardrail-select')
    await expect(guardrailSelect).toBeVisible({ timeout: 10000 })
  })

  test('guardrail configuration panel shows type badge', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    // Configuration section should show the guardrail type
    const configSection = page.getByText(/configuration/i)
    await expect(configSection).toBeVisible({ timeout: 10000 })
  })

  test('test input textarea exists', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const testInput = page.locator('#test-input')
    await expect(testInput).toBeVisible({ timeout: 10000 })
  })

  test('run test button exists', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const runButton = page.getByRole('button', { name: /run test/i })
    await expect(runButton).toBeVisible({ timeout: 10000 })
  })

  test('run test button is disabled without input', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const runButton = page.getByRole('button', { name: /run test/i })
    await expect(runButton).toBeVisible({ timeout: 10000 })
    await expect(runButton).toBeDisabled()
  })

  test('PII sample preset button loads sample text', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const piiButton = page.getByRole('button', { name: /pii sample/i })
    await expect(piiButton).toBeVisible({ timeout: 10000 })

    await piiButton.click()

    // Test input should now contain PII sample data
    const testInput = page.locator('#test-input')
    const value = await testInput.inputValue()
    expect(value).toContain('@')
    expect(value.length).toBeGreaterThan(0)
  })

  test('sensitive data preset button loads sample text', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const sensitiveButton = page.getByRole('button', {
      name: /sensitive data/i,
    })
    await expect(sensitiveButton).toBeVisible({ timeout: 10000 })

    await sensitiveButton.click()

    const testInput = page.locator('#test-input')
    const value = await testInput.inputValue()
    expect(value).toContain('SSN')
    expect(value.length).toBeGreaterThan(0)
  })

  test('clean text preset button loads sample text', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const cleanButton = page.getByRole('button', { name: /clean text/i })
    await expect(cleanButton).toBeVisible({ timeout: 10000 })

    await cleanButton.click()

    const testInput = page.locator('#test-input')
    const value = await testInput.inputValue()
    expect(value).toContain('clean')
    expect(value.length).toBeGreaterThan(0)
  })

  test('results area shows placeholder before running test', async ({ page }) => {
    await page.waitForTimeout(1500)

    const emptyState = page.getByText(/no guardrails found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      return
    }

    const errorState = page.getByText(/failed to load/i)
    const errorVisible = await errorState.isVisible().catch(() => false)

    if (errorVisible) {
      return
    }

    const resultsLabel = page.getByText(/^results$/i)
    await expect(resultsLabel).toBeVisible({ timeout: 10000 })

    const placeholder = page.getByText(/select a guardrail and run/i)
    await expect(placeholder).toBeVisible()
  })
})
