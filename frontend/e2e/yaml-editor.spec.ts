import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('YAML Editor', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('YAML editor toggle button exists', async ({ page }) => {
    const main = page.locator('main')
    const yamlBtn = main.getByRole('button', { name: /yaml/i })
    await expect(yamlBtn).toBeVisible()
  })

  test('YAML editor opens and shows content', async ({ page }) => {
    const main = page.locator('main')
    // Load example crew first
    await main.getByRole('button', { name: /load example/i }).click()
    await expect(main.getByText('Example crew loaded')).toBeVisible()

    // Open YAML editor
    const yamlBtn = main.getByRole('button', { name: /yaml/i })
    await yamlBtn.click()

    // Verify YAML content is visible (apiVersion is a standard YAML field)
    await expect(main.getByText('apiVersion')).toBeVisible()
  })

  test('YAML editor toggle has pressed state', async ({ page }) => {
    const main = page.locator('main')
    const yamlBtn = main.getByRole('button', { name: /yaml/i })

    // Initially not pressed
    await expect(yamlBtn).toHaveAttribute('aria-pressed', 'false')

    // Click to open
    await yamlBtn.click()
    await expect(yamlBtn).toHaveAttribute('aria-pressed', 'true')

    // Click to close
    await yamlBtn.click()
    await expect(yamlBtn).toHaveAttribute('aria-pressed', 'false')
  })
})
