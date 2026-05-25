import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Marketplace Enhanced', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/marketplace')
  })

  test('marketplace page has search input', async ({ page }) => {
    const main = page.locator('main')
    const searchInput = main
      .getByRole('searchbox', { name: /search/i })
      .or(main.getByPlaceholder(/search/i))
    await expect(searchInput).toBeVisible()
  })

  test('category filter chips present', async ({ page }) => {
    const main = page.locator('main')
    const categories = [
      'All',
      'Starter',
      'Content',
      'Support',
      'DevTools',
      'Data',
      'SEO',
    ]

    for (const category of categories) {
      await expect(
        main.getByRole('button', { name: new RegExp(`^${category}$`, 'i') }),
      ).toBeVisible()
    }
  })

  test('featured repos grid shows cards', async ({ page }) => {
    const main = page.locator('main')
    const cards = main.getByRole('article').or(main.locator('[data-testid="marketplace-card"]'))
    await expect(cards.first()).toBeVisible()
  })

  test('each card has Import and Preview buttons', async ({ page }) => {
    const main = page.locator('main')
    const firstCard = main
      .getByRole('article')
      .or(main.locator('[data-testid="marketplace-card"]'))
      .first()
    await expect(firstCard).toBeVisible()

    await expect(
      firstCard.getByRole('button', { name: /import/i }),
    ).toBeVisible()
    await expect(
      firstCard.getByRole('button', { name: /preview/i }),
    ).toBeVisible()
  })

  test('search filters cards by name', async ({ page }) => {
    const main = page.locator('main')
    const searchInput = main
      .getByRole('searchbox', { name: /search/i })
      .or(main.getByPlaceholder(/search/i))
    await searchInput.fill('research')

    await expect(main.getByText(/research/i).first()).toBeVisible()
  })
})
