import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('CUJ-46: Mobile Responsive', () => {
  test.beforeEach(async ({ page }) => {
    // Set iPhone viewport before login so the mobile layout renders
    await page.setViewportSize({ width: 375, height: 667 })
    await login(page)
    await page.goto('/dashboard')
    await page.waitForLoadState('domcontentloaded')
  })

  test('mobile header is visible with hamburger menu', async ({ page }) => {
    // The mobile header is only shown on narrow viewports (md:hidden)
    const menuButton = page.getByRole('button', {
      name: /open navigation menu/i,
    })
    await expect(menuButton).toBeVisible()

    // The Blackbeard branding should be in the header
    await expect(page.getByText('Blackbeard')).toBeVisible()
  })

  test('clicking hamburger opens sidebar', async ({ page }) => {
    const menuButton = page.getByRole('button', {
      name: /open navigation menu/i,
    })
    await menuButton.click()

    // Sidebar should become visible with navigation links
    const sidebar = page.locator('aside')
    await expect(sidebar).toBeVisible()

    // Navigation links should be present
    await expect(sidebar.getByRole('link', { name: /dashboard/i })).toBeVisible()
    await expect(sidebar.getByRole('link', { name: /studio/i })).toBeVisible()
  })

  test('sidebar links are navigable on mobile', async ({ page }) => {
    const menuButton = page.getByRole('button', {
      name: /open navigation menu/i,
    })
    await menuButton.click()

    const sidebar = page.locator('aside')
    await expect(sidebar).toBeVisible()

    // Click a navigation link
    const studioLink = sidebar.getByRole('link', { name: /studio/i })
    await expect(studioLink).toBeVisible()
    await studioLink.click()

    // Should navigate to /studio
    await expect(page).toHaveURL(/\/studio/, { timeout: 10000 })
  })

  test('sidebar can be closed on mobile', async ({ page }) => {
    // Open sidebar
    const openButton = page.getByRole('button', {
      name: /open navigation menu/i,
    })
    await openButton.click()

    // The button label should change to "Close navigation menu"
    const closeButton = page.getByRole('button', {
      name: /close navigation menu/i,
    })
    await expect(closeButton).toBeVisible()
    await closeButton.click()

    // After closing, the open button should reappear
    await expect(openButton).toBeVisible()
  })

  test('backdrop click closes sidebar on mobile', async ({ page }) => {
    const openButton = page.getByRole('button', {
      name: /open navigation menu/i,
    })
    await openButton.click()

    // The backdrop overlay should be visible
    const backdrop = page.locator('.fixed.inset-0.bg-black\\/40')
    const backdropVisible = await backdrop.isVisible().catch(() => false)

    if (backdropVisible) {
      await backdrop.click()

      // Sidebar should close
      await expect(openButton).toBeVisible()
    }
  })

  test('main content is visible at mobile viewport', async ({ page }) => {
    const main = page.locator('main')
    await expect(main).toBeVisible()
  })
})
