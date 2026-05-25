import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Guardrail Playground', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/guardrails/playground')
  })

  test('guardrail playground page loads', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: /guardrail playground/i }),
    ).toBeVisible()
  })

  test('guardrail selector dropdown present', async ({ page }) => {
    const main = page.locator('main')
    const selector = main.getByLabel(/select guardrail/i).or(
      main.getByRole('combobox', { name: /guardrail/i }),
    )
    await expect(selector).toBeVisible()
  })

  test('test input textarea present', async ({ page }) => {
    const main = page.locator('main')
    const textarea = main.getByLabel(/test input/i).or(
      main.getByRole('textbox', { name: /input/i }),
    )
    await expect(textarea).toBeVisible()
  })

  test('run test button present', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByRole('button', { name: /run test/i }),
    ).toBeVisible()
  })
})
