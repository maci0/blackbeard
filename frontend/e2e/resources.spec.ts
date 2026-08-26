import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Resources page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/resources')
  })

  test('displays total resource count', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByText(/\d+ results/)).toBeVisible()
  })

  test('shows kind badges in the table', async ({ page }) => {
    const main = page.locator('main')
    const table = main.getByRole('table', { name: /resources/i })
    await expect(table).toBeVisible()

    // Verify several resource kinds are present
    await expect(main.getByText('Agent').first()).toBeVisible()
    await expect(main.getByText('Task').first()).toBeVisible()
    await expect(main.getByText('Crew').first()).toBeVisible()
    await expect(main.getByText('Tool').first()).toBeVisible()
  })

  test('search filter narrows results', async ({ page }) => {
    const main = page.locator('main')
    const searchInput = main.getByRole('searchbox', { name: /search resources/i })

    // Wait for data to load
    await expect(main.getByRole('table', { name: /resources/i })).toBeVisible()

    // Capture the initial result count text
    const resultStatus = main.getByRole('status', { name: /results/i }).or(
      main.getByText(/\d+ results/),
    )
    await expect(resultStatus.first()).not.toHaveText('0 results')
    const initialText = await resultStatus.first().textContent()

    await searchInput.fill('researcher')

    // Result count should change from initial
    await expect(resultStatus.first()).not.toHaveText(initialText ?? '')

    // At least one result should contain the search term
    await expect(main.getByText(/researcher/i).first()).toBeVisible()
  })

  test('kind dropdown filter works', async ({ page }) => {
    const main = page.locator('main')
    const kindFilter = main.getByLabel(/filter by kind/i)

    // Wait for data to load
    await expect(main.getByRole('table', { name: /resources/i })).toBeVisible()

    const resultStatus = main.getByRole('status', { name: /results/i }).or(
      main.getByText(/\d+ results/),
    )
    await expect(resultStatus.first()).not.toHaveText('0 results')
    const initialText = await resultStatus.first().textContent()

    await kindFilter.selectOption({ label: 'Agent' })

    // Result count should change
    await expect(resultStatus.first()).not.toHaveText(initialText ?? '')

    // Clear filters button should appear
    await expect(main.getByRole('button', { name: /clear/i })).toBeVisible()
  })

  test('clear filters resets to full list', async ({ page }) => {
    const main = page.locator('main')

    // Wait for data to load: table must be visible before capturing count
    await expect(main.getByRole('table', { name: /resources/i })).toBeVisible()

    const resultStatus = main.getByRole('status', { name: /results/i }).or(
      main.getByText(/\d+ results/),
    )

    // Wait for a non-zero count before capturing
    await expect(resultStatus.first()).not.toHaveText('0 results')

    // Capture the initial (full) result count
    const initialText = await resultStatus.first().textContent()

    const searchInput = main.getByRole('searchbox', { name: /search resources/i })
    await searchInput.fill('researcher')

    await expect(resultStatus.first()).not.toHaveText(initialText ?? '')

    await main.getByRole('button', { name: /clear/i }).click()

    await expect(resultStatus.first()).toHaveText(initialText ?? '')
  })

  test('page header shows title and description', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Resources' })).toBeVisible()
    await expect(
      main.getByText('Agents, tasks, crews, tools, and policies'),
    ).toBeVisible()
  })
})
