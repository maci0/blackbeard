import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Settings page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/settings')
  })

  test('page loads with sections', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Settings' }),
    ).toBeVisible()
    await expect(
      main.getByText('Configure your Blackbeard instance'),
    ).toBeVisible()
  })

  test('API Connection section present', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'API Connection' }),
    ).toBeVisible()
    await expect(main.getByLabel('API base URL')).toBeVisible()
    await expect(
      main.getByRole('button', { name: /save/i }),
    ).toBeVisible()
  })

  test('Services section with links', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Services' }),
    ).toBeVisible()
    await expect(
      main.getByText('/api/v1/health'),
    ).toBeVisible()
    await expect(
      main.getByText(':4000/ui'),
    ).toBeVisible()
    await expect(
      main.getByText('/api/v1/docs'),
    ).toBeVisible()
  })

  test('Authentication section shows status', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Authentication' }),
    ).toBeVisible()
    await expect(main.getByText('SSO / OIDC')).toBeVisible()
    await expect(main.getByText('Auth method')).toBeVisible()
  })

  test('Preferences section has notification toggles', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Preferences' }),
    ).toBeVisible()

    const browserNotifSwitch = main.getByRole('switch', {
      name: /browser notifications/i,
    })
    await expect(browserNotifSwitch).toBeVisible()

    const soundNotifSwitch = main.getByRole('switch', {
      name: /sound on notification/i,
    })
    await expect(soundNotifSwitch).toBeVisible()
  })
})
