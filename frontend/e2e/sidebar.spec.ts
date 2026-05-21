import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Sidebar', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('all nav links are present', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: /primary/i })

    const expectedLinks = [
      'Studio',
      'Resources',
      'Executions',
      'Models',
      'Tools',
      'Users',
      'Roles',
      'Marketplace',
      'Automations',
    ]

    for (const label of expectedLinks) {
      await expect(nav.getByRole('link', { name: label })).toBeVisible()
    }
  })

  test('collapse sidebar hides labels and shows icons', async ({ page }) => {
    const collapseBtn = page.getByRole('button', { name: /collapse sidebar/i })
    await collapseBtn.click()

    // After collapsing, nav links should still be accessible but labels hidden (sr-only)
    const expandBtn = page.getByRole('button', { name: /expand sidebar/i })
    await expect(expandBtn).toBeVisible()

    // Nav links should still exist (accessible by aria-label)
    const nav = page.getByRole('navigation', { name: /primary/i })
    await expect(nav.getByRole('link', { name: 'Studio' })).toBeVisible()
  })

  test('expand sidebar restores labels', async ({ page }) => {
    // Collapse first
    await page.getByRole('button', { name: /collapse sidebar/i }).click()

    // Then expand
    await page.getByRole('button', { name: /expand sidebar/i }).click()

    // Collapse button should be visible again
    await expect(
      page.getByRole('button', { name: /collapse sidebar/i }),
    ).toBeVisible()

    // Labels should be visible
    const nav = page.getByRole('navigation', { name: /primary/i })
    await expect(nav.getByText('Studio')).toBeVisible()
    await expect(nav.getByText('Resources')).toBeVisible()
  })

  test('user avatar/info is visible at bottom', async ({ page }) => {
    // User email or name from the login helper
    await expect(page.getByText('e2e@test.com')).toBeVisible()
  })

  test('theme toggle cycles through modes', async ({ page }) => {
    const themeBtn = page.getByRole('button', { name: /theme/i })
    await expect(themeBtn).toBeVisible()

    const initialLabel = await themeBtn.getAttribute('aria-label')

    await themeBtn.click()

    const newLabel = await themeBtn.getAttribute('aria-label')
    expect(newLabel).not.toBe(initialLabel)
  })

  test('sign out button is visible', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /sign out/i }),
    ).toBeVisible()
  })

  test('version number is shown', async ({ page }) => {
    await expect(page.getByText('v0.1.0')).toBeVisible()
  })

  test('branding logo links to studio', async ({ page }) => {
    const brandBtn = page.getByRole('button', { name: /go to studio/i })
    await expect(brandBtn).toBeVisible()
  })

  test('active link has visual distinction', async ({ page }) => {
    // On /studio after login, Studio link should have active class
    const studioLink = page
      .getByRole('navigation', { name: /primary/i })
      .getByRole('link', { name: 'Studio' })

    await expect(studioLink).toHaveClass(/bg-accent/)
  })

  test('clicking nav links updates active state', async ({ page }) => {
    await page.getByRole('link', { name: 'Resources' }).click()
    await page.waitForURL('/resources')

    const resourcesLink = page
      .getByRole('navigation', { name: /primary/i })
      .getByRole('link', { name: 'Resources' })

    await expect(resourcesLink).toHaveClass(/bg-accent/)
  })
})
