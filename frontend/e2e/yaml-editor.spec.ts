import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('YAML Editor', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('YAML editor toggle button exists', async ({ page }) => {
    const yamlBtn = page.getByRole('button', { name: /yaml/i })
    await expect(yamlBtn).toBeVisible()
  })

  test('YAML editor opens and shows content', async ({ page }) => {
    // Load example crew first
    await page.getByRole('button', { name: /load example/i }).click()
    await expect(page.getByText('Example crew loaded')).toBeVisible()

    // Open YAML editor
    const yamlBtn = page.getByRole('button', { name: /yaml/i })
    await yamlBtn.click()

    // Verify YAML content is visible (apiVersion is a standard YAML field)
    await expect(page.getByText('apiVersion')).toBeVisible()
  })

  test('YAML editor toggle has pressed state', async ({ page }) => {
    const yamlBtn = page.getByRole('button', { name: /yaml/i })

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
