import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('sidebar contains all nav links', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: /primary/i })

    const expectedLinks = [
      'Studio',
      'Resources',
      'Executions',
      'Models',
      'Tools',
      'Users',
      'Roles',
    ]

    for (const label of expectedLinks) {
      await expect(nav.getByRole('link', { name: label })).toBeVisible()
    }
  })

  test('clicking Resources nav link navigates to resources page', async ({
    page,
  }) => {
    await page.getByRole('link', { name: 'Resources' }).click()
    await expect(page).toHaveURL('/resources')
    await expect(page).toHaveTitle(/resources/i)
  })

  test('clicking Executions nav link navigates to executions page', async ({
    page,
  }) => {
    await page.getByRole('link', { name: 'Executions' }).click()
    await expect(page).toHaveURL('/executions')
    await expect(page).toHaveTitle(/executions/i)
  })

  test('clicking Models nav link navigates to models page', async ({
    page,
  }) => {
    await page.getByRole('link', { name: 'Models' }).click()
    await expect(page).toHaveURL('/models')
    await expect(page).toHaveTitle(/models/i)
  })

  test('clicking Roles nav link navigates to roles page', async ({ page }) => {
    await page.getByRole('link', { name: 'Roles' }).click()
    await expect(page).toHaveURL('/roles')
    await expect(page).toHaveTitle(/roles/i)
  })

  test('clicking Users nav link navigates to users page', async ({ page }) => {
    await page.getByRole('link', { name: 'Users' }).click()
    await expect(page).toHaveURL('/users')
    await expect(page).toHaveTitle(/users/i)
  })

  test('clicking Tools nav link navigates to tools page', async ({ page }) => {
    await page.getByRole('link', { name: 'Tools' }).click()
    await expect(page).toHaveURL('/tools')
    await expect(page).toHaveTitle(/tools/i)
  })

  test('sidebar collapse and expand works', async ({ page }) => {
    // Find the collapse button
    const collapseBtn = page.getByRole('button', { name: /collapse sidebar/i })
    await expect(collapseBtn).toBeVisible()

    await collapseBtn.click()

    // After collapsing, the expand button should be visible
    const expandBtn = page.getByRole('button', { name: /expand sidebar/i })
    await expect(expandBtn).toBeVisible()

    await expandBtn.click()

    // After expanding, the collapse button should be visible again
    await expect(
      page.getByRole('button', { name: /collapse sidebar/i }),
    ).toBeVisible()
  })

  test('dark mode toggle cycles through themes', async ({ page }) => {
    // Click the theme toggle button
    const themeBtn = page.getByRole('button', { name: /theme/i })
    await expect(themeBtn).toBeVisible()

    // Get initial theme state
    const initialLabel = await themeBtn.getAttribute('aria-label')

    // Click to cycle
    await themeBtn.click()

    // Label should change after cycling
    const newLabel = await themeBtn.getAttribute('aria-label')
    expect(newLabel).not.toBe(initialLabel)
  })

  test('navigating to unknown route shows 404 page', async ({ page }) => {
    await page.goto('/nonexistent-page')

    const main = page.locator('main')
    await expect(main.getByText('Page not found')).toBeVisible()
    await expect(main.getByRole('link', { name: /go to studio/i })).toBeVisible()
    await expect(
      main.getByRole('link', { name: /browse resources/i }),
    ).toBeVisible()
  })

  test('active nav link is visually distinct', async ({ page }) => {
    await page.goto('/studio')

    // On /studio, the Studio link should be active
    const studioLink = page
      .getByRole('navigation', { name: /primary/i })
      .getByRole('link', { name: 'Studio' })

    // Active link has bg-accent class applied via NavLink isActive
    await expect(studioLink).toHaveClass(/bg-accent/)
  })
})
