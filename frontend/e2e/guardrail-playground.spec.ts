import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Guardrail Playground', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/guardrails/playground')
  })

  test('guardrail playground page loads', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /guardrail playground/i }),
    ).toBeVisible()
  })

  test('guardrail selector dropdown present', async ({ page }) => {
    const selector = page.getByLabel(/select guardrail/i).or(
      page.getByRole('combobox', { name: /guardrail/i }),
    )
    await expect(selector).toBeVisible()
  })

  test('test input textarea present', async ({ page }) => {
    const textarea = page.getByLabel(/test input/i).or(
      page.getByRole('textbox', { name: /input/i }),
    )
    await expect(textarea).toBeVisible()
  })

  test('run test button present', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /run test/i }),
    ).toBeVisible()
  })
})
