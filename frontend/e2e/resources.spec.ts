import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Resources page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: 'Resources' }).click()
    await page.waitForURL('/resources')
  })

  test('displays total resource count', async ({ page }) => {
    await expect(page.getByText('31 results')).toBeVisible()
  })

  test('shows kind badges in the table', async ({ page }) => {
    const table = page.getByRole('table', { name: /resources/i })
    await expect(table).toBeVisible()

    // Verify several resource kinds are present
    await expect(page.getByText('Agent').first()).toBeVisible()
    await expect(page.getByText('Task').first()).toBeVisible()
    await expect(page.getByText('Crew').first()).toBeVisible()
    await expect(page.getByText('Tool').first()).toBeVisible()
  })

  test('search filter narrows results', async ({ page }) => {
    const searchInput = page.getByRole('searchbox', { name: /search resources/i })
    await searchInput.fill('researcher')

    // Result count should decrease
    const resultStatus = page.getByRole('status')
    await expect(resultStatus).not.toHaveText('31 results')

    // At least one result should contain the search term
    await expect(page.getByText(/researcher/i).first()).toBeVisible()
  })

  test('kind dropdown filter works', async ({ page }) => {
    const kindFilter = page.getByLabel(/filter by kind/i)
    await kindFilter.selectOption({ label: 'Agent' })

    // All visible rows should be Agent kind
    const resultStatus = page.getByRole('status')
    await expect(resultStatus).not.toHaveText('31 results')

    // Clear filters button should appear
    await expect(page.getByRole('button', { name: /clear/i })).toBeVisible()
  })

  test('clear filters resets to full list', async ({ page }) => {
    const searchInput = page.getByRole('searchbox', { name: /search resources/i })
    await searchInput.fill('researcher')

    await expect(page.getByRole('status')).not.toHaveText('31 results')

    await page.getByRole('button', { name: /clear/i }).click()

    await expect(page.getByRole('status')).toHaveText('31 results')
  })

  test('page header shows title and description', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Resources' })).toBeVisible()
    await expect(
      page.getByText('Agents, tasks, crews, tools, and policies'),
    ).toBeVisible()
  })
})
