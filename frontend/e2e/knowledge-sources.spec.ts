import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Knowledge Sources page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/knowledge-sources')
  })

  test('page loads with title', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Knowledge Sources' }),
    ).toBeVisible()
    await expect(
      page.getByText('RAG knowledge sources for agent memory and context'),
    ).toBeVisible()
  })

  test('add source dialog opens', async ({ page }) => {
    await page
      .getByRole('button', { name: /add knowledge source/i })
      .click()

    await expect(
      page.getByRole('heading', { name: 'Add Knowledge Source' }),
    ).toBeVisible()
    await expect(page.getByLabel(/^Name/)).toBeVisible()
    await expect(page.getByLabel(/Source Type/)).toBeVisible()
  })

  test('add source dialog can be closed', async ({ page }) => {
    await page
      .getByRole('button', { name: /add knowledge source/i })
      .click()

    await expect(
      page.getByRole('heading', { name: 'Add Knowledge Source' }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(
      page.getByRole('heading', { name: 'Add Knowledge Source' }),
    ).not.toBeVisible()
  })

  test('empty state shows when no sources', async ({ page }) => {
    const cards = page.locator('[class*="grid"] [class*="rounded-lg"]')
    const emptyState = page.getByText('No knowledge sources configured')

    await expect(cards.first().or(emptyState)).toBeVisible()
  })
})
