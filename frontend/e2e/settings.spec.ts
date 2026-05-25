import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Settings page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/settings')
  })

  test('page loads with sections', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Settings' }),
    ).toBeVisible()
    await expect(
      page.getByText('Configure your Blackbeard instance'),
    ).toBeVisible()
  })

  test('API Connection section present', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'API Connection' }),
    ).toBeVisible()
    await expect(page.getByLabel('API base URL')).toBeVisible()
    await expect(
      page.getByRole('button', { name: /save/i }),
    ).toBeVisible()
  })

  test('Services section with links', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Services' }),
    ).toBeVisible()
    await expect(
      page.getByRole('link', { name: /\/api\/v1\/health/i }),
    ).toBeVisible()
    await expect(
      page.getByRole('link', { name: /:4000\/ui/i }),
    ).toBeVisible()
    await expect(
      page.getByRole('link', { name: /\/api\/v1\/docs/i }),
    ).toBeVisible()
  })

  test('Authentication section shows status', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Authentication' }),
    ).toBeVisible()
    await expect(page.getByText('SSO / OIDC')).toBeVisible()
    await expect(page.getByText('Auth method')).toBeVisible()
  })

  test('Preferences section has notification toggles', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Preferences' }),
    ).toBeVisible()

    const browserNotifSwitch = page.getByRole('switch', {
      name: /browser notifications/i,
    })
    await expect(browserNotifSwitch).toBeVisible()

    const soundNotifSwitch = page.getByRole('switch', {
      name: /sound on notification/i,
    })
    await expect(soundNotifSwitch).toBeVisible()
  })
})
