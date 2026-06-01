import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('CUJ-45: Dark Mode Toggle', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    // Reset theme to a known state
    await page.evaluate(() => localStorage.removeItem('blackbeard_theme'))
  })

  test('theme toggle button is visible in sidebar', async ({ page }) => {
    // The theme toggle sits in the sidebar footer area
    const themeButton = page.getByRole('button', {
      name: /theme.*click to cycle/i,
    })
    await expect(themeButton).toBeVisible()
  })

  test('clicking theme toggle cycles through preferences', async ({ page }) => {
    const themeButton = page.getByRole('button', {
      name: /theme.*click to cycle/i,
    })
    await expect(themeButton).toBeVisible()

    // Get the initial preference from the aria-label
    const initialLabel = await themeButton.getAttribute('aria-label')

    // Click to cycle
    await themeButton.click()

    // The aria-label should change (preference cycled)
    const afterFirstClick = await themeButton.getAttribute('aria-label')
    expect(afterFirstClick).not.toBe(initialLabel)

    // Click again
    await themeButton.click()

    const afterSecondClick = await themeButton.getAttribute('aria-label')
    expect(afterSecondClick).not.toBe(afterFirstClick)
  })

  test('dark mode applies dark class to document', async ({ page }) => {
    // Set theme to dark via localStorage, then reload
    await page.evaluate(() => localStorage.setItem('blackbeard_theme', 'dark'))
    await page.reload()
    await page.waitForLoadState('domcontentloaded')

    const hasDarkClass = await page.evaluate(() =>
      document.documentElement.classList.contains('dark'),
    )
    expect(hasDarkClass).toBe(true)
  })

  test('light mode removes dark class from document', async ({ page }) => {
    await page.evaluate(() => localStorage.setItem('blackbeard_theme', 'light'))
    await page.reload()
    await page.waitForLoadState('domcontentloaded')

    const hasDarkClass = await page.evaluate(() =>
      document.documentElement.classList.contains('dark'),
    )
    expect(hasDarkClass).toBe(false)
  })

  test('key page elements remain visible after theme toggle', async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/dashboard')
    await page.waitForLoadState('domcontentloaded')

    const themeButton = page.getByRole('button', {
      name: /theme.*click to cycle/i,
    })

    // Toggle theme
    await themeButton.click()
    await page.waitForTimeout(300)

    // Core sidebar elements should still be visible
    await expect(page.getByText('Blackbeard')).toBeVisible()
    await expect(page.locator('main')).toBeVisible()

    // Toggle again
    await themeButton.click()
    await page.waitForTimeout(300)

    await expect(page.getByText('Blackbeard')).toBeVisible()
    await expect(page.locator('main')).toBeVisible()
  })

  test('theme preference persists to localStorage', async ({ page }) => {
    const themeButton = page.getByRole('button', {
      name: /theme.*click to cycle/i,
    })

    // Cycle to get a known state
    await themeButton.click()

    const storedTheme = await page.evaluate(() => localStorage.getItem('blackbeard_theme'))
    expect(['system', 'dark', 'light']).toContain(storedTheme)
  })
})
