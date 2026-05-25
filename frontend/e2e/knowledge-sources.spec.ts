import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Knowledge Sources page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/knowledge-sources')
  })

  test('page loads with title', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Knowledge Sources' }),
    ).toBeVisible()
    await expect(
      main.getByText('RAG knowledge sources for agent memory and context'),
    ).toBeVisible()
  })

  test('add source dialog opens', async ({ page }) => {
    const main = page.locator('main')
    await main
      .getByRole('button', { name: /add knowledge source/i })
      .click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Knowledge Source' }),
    ).toBeVisible()
    await expect(page.getByLabel(/^Name/)).toBeVisible()
    await expect(page.getByLabel(/Source Type/)).toBeVisible()
  })

  test('add source dialog can be closed', async ({ page }) => {
    const main = page.locator('main')
    await main
      .getByRole('button', { name: /add knowledge source/i })
      .click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Knowledge Source' }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Knowledge Source' }),
    ).not.toBeVisible()
  })

  test('empty state shows when no sources', async ({ page }) => {
    const main = page.locator('main')
    const cards = main.locator('[class*="grid"] [class*="rounded-lg"]')
    const emptyState = main.getByText('No knowledge sources configured')

    await expect(cards.first().or(emptyState)).toBeVisible()
  })
})
