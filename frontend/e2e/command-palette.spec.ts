import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Command Palette', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('Cmd+K opens command palette', async ({ page }) => {
    await page.keyboard.press('Meta+k')

    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).toBeVisible()
  })

  test('search input focuses automatically', async ({ page }) => {
    await page.keyboard.press('Meta+k')

    const searchInput = page.getByRole('combobox', { name: /search/i })
    await expect(searchInput).toBeVisible()
    await expect(searchInput).toBeFocused()
  })

  test('navigation items listed', async ({ page }) => {
    await page.keyboard.press('Meta+k')

    const dialog = page.getByRole('dialog', { name: /command palette/i })
    await expect(dialog).toBeVisible()

    const expectedPages = [
      'Dashboard',
      'Studio',
      'Resources',
      'Executions',
      'Models',
      'Chat',
      'Tools',
      'Users',
      'Roles',
      'Audit Logs',
      'Marketplace',
      'Settings',
    ]

    for (const pageName of expectedPages) {
      await expect(
        dialog.getByRole('option', { name: new RegExp(pageName) }),
      ).toBeVisible()
    }
  })

  test('Escape closes palette', async ({ page }) => {
    await page.keyboard.press('Meta+k')

    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).toBeVisible()

    await page.keyboard.press('Escape')

    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).not.toBeVisible()
  })
})
