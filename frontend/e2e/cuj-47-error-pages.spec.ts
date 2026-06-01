import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('CUJ-47: Error Pages', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('navigating to nonexistent page shows 404', async ({ page }) => {
    await page.goto('/nonexistent-page-abc123')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByText('Page not found')).toBeVisible()
    await expect(page.getByText('404')).toBeVisible()
  })

  test('404 page shows descriptive message', async ({ page }) => {
    await page.goto('/this-route-does-not-exist')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByText(/doesn.t exist|may have been moved/i)).toBeVisible()
  })

  test('404 page has Go to Studio link', async ({ page }) => {
    await page.goto('/nonexistent-page')
    await page.waitForLoadState('domcontentloaded')

    const studioLink = page.getByRole('link', { name: /go to studio/i })
    await expect(studioLink).toBeVisible()
    await expect(studioLink).toHaveAttribute('href', '/studio')
  })

  test('404 page has Browse Resources link', async ({ page }) => {
    await page.goto('/nonexistent-page')
    await page.waitForLoadState('domcontentloaded')

    const resourcesLink = page.getByRole('link', {
      name: /browse resources/i,
    })
    await expect(resourcesLink).toBeVisible()
    await expect(resourcesLink).toHaveAttribute('href', '/resources')
  })

  test('Go to Studio link navigates correctly', async ({ page }) => {
    await page.goto('/nonexistent-page')
    await page.waitForLoadState('domcontentloaded')

    await page.getByRole('link', { name: /go to studio/i }).click()
    await expect(page).toHaveURL(/\/studio/, { timeout: 10000 })
  })

  test('Browse Resources link navigates correctly', async ({ page }) => {
    await page.goto('/another-fake-route')
    await page.waitForLoadState('domcontentloaded')

    await page.getByRole('link', { name: /browse resources/i }).click()
    await expect(page).toHaveURL(/\/resources/, { timeout: 10000 })
  })

  test('deeply nested nonexistent route shows 404', async ({ page }) => {
    await page.goto('/some/deeply/nested/nonexistent/route')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByText('Page not found')).toBeVisible()
  })
})
