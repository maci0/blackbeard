import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Execution Compare', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('compare page loads and shows error without params', async ({
    page,
  }) => {
    await page.goto('/executions/compare')

    const main = page.locator('main')
    await expect(
      main.getByText(/select.*executions|no executions selected/i),
    ).toBeVisible()
  })

  test('with invalid IDs shows error state', async ({ page }) => {
    await page.goto(
      '/executions/compare?ids=00000000-0000-0000-0000-000000000000,00000000-0000-0000-0000-000000000001',
    )

    const main = page.locator('main')
    await expect(
      main.getByText(/not found|failed to load|error/i),
    ).toBeVisible()
  })

  test('page has comparison layout structure', async ({ page }) => {
    await page.goto('/executions/compare')

    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: /compare/i }),
    ).toBeVisible()
  })
})
