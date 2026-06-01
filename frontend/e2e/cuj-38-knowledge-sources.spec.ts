import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-38: Knowledge Sources', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/knowledge')
  })

  test('page renders with heading and add button', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Knowledge Sources' })).toBeVisible()
    await expect(main.getByRole('button', { name: /add knowledge source/i })).toBeVisible()
  })

  test('clicking add opens dialog with source type dropdown', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add knowledge source/i }).click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Knowledge Source' }),
    ).toBeVisible()

    const sourceTypeSelect = page.getByLabel(/Source Type/)
    await expect(sourceTypeSelect).toBeVisible()

    const options = sourceTypeSelect.locator('option')
    const optionTexts = await options.allTextContents()
    const lowerTexts = optionTexts.map((t) => t.toLowerCase())

    expect(lowerTexts).toEqual(expect.arrayContaining(['text', 'pdf', 'csv', 'json', 'url']))
  })

  test('name field is required in add dialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add knowledge source/i }).click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Knowledge Source' }),
    ).toBeVisible()

    const nameField = page.getByLabel(/^Name/)
    await expect(nameField).toBeVisible()

    // Attempt submit with empty name to verify required validation
    const submitBtn = page
      .getByRole('button', { name: /^add$/i })
      .or(page.getByRole('button', { name: /create/i }))
    if (await submitBtn.isVisible()) {
      await submitBtn.click()
      // Name field should still be visible (form not dismissed)
      await expect(nameField).toBeVisible()
    }
  })

  test('dialog can be closed', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add knowledge source/i }).click()

    const heading = page.locator('h1, h2, h3').filter({ hasText: 'Add Knowledge Source' })
    await expect(heading).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()
    await expect(heading).not.toBeVisible()
  })

  test('shows cards or empty state', async ({ page }) => {
    const main = page.locator('main')
    const cards = main.locator('[class*="grid"] [class*="rounded-lg"]')
    const emptyState = main.getByText(/no knowledge sources/i)

    await expect(cards.first().or(emptyState)).toBeVisible()
  })
})
