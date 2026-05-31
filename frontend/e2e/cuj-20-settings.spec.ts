import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-20: Settings and Preferences', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/settings')
  })

  test('page renders with Settings heading', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Settings' }),
    ).toBeVisible()
    await expect(
      main.getByText('Configure your Blackbeard instance'),
    ).toBeVisible()
  })

  test('Preferences section is visible', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Preferences' }),
    ).toBeVisible()
  })

  test('browser notifications toggle is visible', async ({ page }) => {
    const main = page.locator('main')
    const browserNotifSwitch = main.getByRole('switch', {
      name: /browser notifications/i,
    })
    await expect(browserNotifSwitch).toBeVisible()
  })

  test('sound on notification toggle is visible', async ({ page }) => {
    const main = page.locator('main')
    const soundNotifSwitch = main.getByRole('switch', {
      name: /sound on notification/i,
    })
    await expect(soundNotifSwitch).toBeVisible()
  })

  test('toggling browser notifications persists to localStorage', async ({
    page,
  }) => {
    const main = page.locator('main')
    const browserNotifSwitch = main.getByRole('switch', {
      name: /browser notifications/i,
    })

    // Get the initial state
    const initialChecked = await browserNotifSwitch.isChecked()

    // Toggle it
    await browserNotifSwitch.click()

    // The switch state should flip
    if (initialChecked) {
      await expect(browserNotifSwitch).not.toBeChecked()
    } else {
      await expect(browserNotifSwitch).toBeChecked()
    }

    // Verify localStorage was updated
    const storedValue = await page.evaluate(() =>
      localStorage.getItem('blackbeard_browser_notifications'),
    )
    const expectedValue = initialChecked ? 'false' : 'true'
    expect(storedValue).toBe(expectedValue)
  })

  test('toggling sound notification persists to localStorage', async ({
    page,
  }) => {
    const main = page.locator('main')
    const soundSwitch = main.getByRole('switch', {
      name: /sound on notification/i,
    })

    const initialChecked = await soundSwitch.isChecked()

    await soundSwitch.click()

    if (initialChecked) {
      await expect(soundSwitch).not.toBeChecked()
    } else {
      await expect(soundSwitch).toBeChecked()
    }

    const storedValue = await page.evaluate(() =>
      localStorage.getItem('blackbeard_sound_notifications'),
    )
    const expectedValue = initialChecked ? 'false' : 'true'
    expect(storedValue).toBe(expectedValue)
  })

  test('API Connection section has base URL input and save button', async ({
    page,
  }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'API Connection' }),
    ).toBeVisible()
    await expect(main.getByLabel('API base URL')).toBeVisible()
    await expect(
      main.getByRole('button', { name: /save/i }),
    ).toBeVisible()
  })

  test('Authentication section shows auth method info', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Authentication' }),
    ).toBeVisible()
    await expect(main.getByText('Auth method')).toBeVisible()
  })

  test('Services section has expected links', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Services' }),
    ).toBeVisible()
    await expect(main.getByText('/api/v1/health')).toBeVisible()
    await expect(main.getByText(':4000/ui')).toBeVisible()
    await expect(main.getByText('/api/v1/docs')).toBeVisible()
  })
})
