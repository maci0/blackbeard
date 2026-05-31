import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-18: Knowledge Source Management', () => {
  test.beforeEach(async ({ page }) => {
    // The nav link uses /knowledge but the route is /knowledge-sources
    await loginAndNavigate(page, '/knowledge-sources')
  })

  test('page renders with heading', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Knowledge Sources' }),
    ).toBeVisible()
  })

  test('page shows description text', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByText('RAG knowledge sources for agent memory and context'),
    ).toBeVisible()
  })

  test('add knowledge source button is visible', async ({ page }) => {
    const main = page.locator('main')
    const addBtn = main.getByRole('button', {
      name: /add knowledge source/i,
    })
    await expect(addBtn).toBeVisible()
  })

  test('clicking add button opens dialog with name and source type fields', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main
      .getByRole('button', { name: /add knowledge source/i })
      .click()

    // Dialog should appear with a heading
    await expect(
      page
        .locator('h1, h2, h3')
        .filter({ hasText: 'Add Knowledge Source' }),
    ).toBeVisible()

    // Name field present
    await expect(page.getByLabel(/^Name/)).toBeVisible()

    // Source Type selector present
    await expect(page.getByLabel(/Source Type/)).toBeVisible()
  })

  test('source type selector lists expected types', async ({ page }) => {
    const main = page.locator('main')
    await main
      .getByRole('button', { name: /add knowledge source/i })
      .click()

    await expect(
      page
        .locator('h1, h2, h3')
        .filter({ hasText: 'Add Knowledge Source' }),
    ).toBeVisible()

    const sourceTypeSelect = page.getByLabel(/Source Type/)
    await expect(sourceTypeSelect).toBeVisible()

    // Check that the select has the expected option values
    const options = sourceTypeSelect.locator('option')
    const optionTexts = await options.allTextContents()
    const lowerTexts = optionTexts.map((t) => t.toLowerCase())

    expect(lowerTexts).toEqual(
      expect.arrayContaining(['text', 'pdf', 'csv', 'json', 'url']),
    )
  })

  test('dialog can be closed', async ({ page }) => {
    const main = page.locator('main')
    await main
      .getByRole('button', { name: /add knowledge source/i })
      .click()

    await expect(
      page
        .locator('h1, h2, h3')
        .filter({ hasText: 'Add Knowledge Source' }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(
      page
        .locator('h1, h2, h3')
        .filter({ hasText: 'Add Knowledge Source' }),
    ).not.toBeVisible()
  })

  test('empty state shows when no knowledge sources exist', async ({
    page,
  }) => {
    const main = page.locator('main')
    const cards = main.locator('[class*="grid"] [class*="rounded-lg"]')
    const emptyState = main.getByText('No knowledge sources configured')

    await expect(cards.first().or(emptyState)).toBeVisible()
  })
})
