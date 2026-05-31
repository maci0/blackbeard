import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-13: Guardrail Testing', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/guardrails/playground')
  })

  test('page renders with heading and description', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /guardrail playground/i }),
    ).toBeVisible()
  })

  test('shows guardrail selector or empty state when no guardrails exist', async ({
    page,
  }) => {
    // The page shows either the guardrail selector (when resources exist)
    // or the empty state message
    const selector = page.getByLabel(/guardrail/i)
    const emptyMessage = page.getByText(/no guardrails found/i)
    const loadingSpinner = page.getByText(/loading guardrails/i)

    // Wait for loading to finish
    if (await loadingSpinner.isVisible()) {
      await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })
    }

    await expect(selector.or(emptyMessage)).toBeVisible()
  })

  test('test input textarea is visible when guardrails exist', async ({
    page,
  }) => {
    const emptyMessage = page.getByText(/no guardrails found/i)
    const loadingSpinner = page.getByText(/loading guardrails/i)

    // Wait for loading to finish
    if (await loadingSpinner.isVisible()) {
      await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })
    }

    // Only check for input area if guardrails exist
    if (!(await emptyMessage.isVisible())) {
      const testInput = page.getByLabel(/test input/i)
      await expect(testInput).toBeVisible()

      // Placeholder text guides the user
      await expect(testInput).toHaveAttribute(
        'placeholder',
        /enter text to test/i,
      )
    }
  })

  test('run test button is visible when guardrails exist', async ({
    page,
  }) => {
    const emptyMessage = page.getByText(/no guardrails found/i)
    const loadingSpinner = page.getByText(/loading guardrails/i)

    if (await loadingSpinner.isVisible()) {
      await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })
    }

    if (!(await emptyMessage.isVisible())) {
      const runButton = page.getByRole('button', { name: /run test/i })
      await expect(runButton).toBeVisible()

      // Should be disabled when no input text is entered
      await expect(runButton).toBeDisabled()
    }
  })

  test('sample input buttons are visible when guardrails exist', async ({
    page,
  }) => {
    const emptyMessage = page.getByText(/no guardrails found/i)
    const loadingSpinner = page.getByText(/loading guardrails/i)

    if (await loadingSpinner.isVisible()) {
      await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })
    }

    if (!(await emptyMessage.isVisible())) {
      await expect(
        page.getByRole('button', { name: /pii sample/i }),
      ).toBeVisible()
      await expect(
        page.getByRole('button', { name: /sensitive data/i }),
      ).toBeVisible()
      await expect(
        page.getByRole('button', { name: /clean text/i }),
      ).toBeVisible()
    }
  })

  test('clicking sample button populates the input', async ({ page }) => {
    const emptyMessage = page.getByText(/no guardrails found/i)
    const loadingSpinner = page.getByText(/loading guardrails/i)

    if (await loadingSpinner.isVisible()) {
      await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })
    }

    if (!(await emptyMessage.isVisible())) {
      await page.getByRole('button', { name: /pii sample/i }).click()

      const testInput = page.getByLabel(/test input/i)
      await expect(testInput).not.toBeEmpty()
      await expect(testInput).toHaveValue(/john\.doe@example\.com/i)

      // Run test button should now be enabled
      await expect(
        page.getByRole('button', { name: /run test/i }),
      ).toBeEnabled()
    }
  })

  test('results area shows placeholder before running a test', async ({
    page,
  }) => {
    const emptyMessage = page.getByText(/no guardrails found/i)
    const loadingSpinner = page.getByText(/loading guardrails/i)

    if (await loadingSpinner.isVisible()) {
      await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })
    }

    if (!(await emptyMessage.isVisible())) {
      await expect(
        page.getByText(/select a guardrail and run a test/i),
      ).toBeVisible()
    }
  })

  test('empty state shows create suggestion', async ({ page }) => {
    const emptyMessage = page.getByText(/no guardrails found/i)
    const loadingSpinner = page.getByText(/loading guardrails/i)

    if (await loadingSpinner.isVisible()) {
      await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })
    }

    if (await emptyMessage.isVisible()) {
      await expect(
        page.getByText(/create a guardrail resource first/i),
      ).toBeVisible()
    }
  })
})
