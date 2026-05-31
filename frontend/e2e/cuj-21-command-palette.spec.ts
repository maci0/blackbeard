import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-21: Command Palette', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('Cmd+K opens command palette dialog', async ({ page }) => {
    await page.keyboard.press('Meta+k')

    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).toBeVisible()
  })

  test('search input is focused automatically on open', async ({ page }) => {
    await page.keyboard.press('Meta+k')

    const dialog = page.getByRole('dialog', { name: /command palette/i })
    const searchInput = dialog.getByRole('combobox', { name: /search/i })
    await expect(searchInput).toBeVisible()
    await expect(searchInput).toBeFocused()
  })

  test('typing "exec" filters results to show Executions', async ({
    page,
  }) => {
    await page.keyboard.press('Meta+k')

    const dialog = page.getByRole('dialog', { name: /command palette/i })
    const searchInput = dialog.getByRole('combobox', { name: /search/i })

    await searchInput.fill('exec')

    // Executions page should appear in filtered results
    await expect(
      dialog.getByRole('option', { name: /executions/i }),
    ).toBeVisible()

    // Pages that do not match "exec" should be hidden
    await expect(
      dialog.getByRole('option', { name: 'Dashboard', exact: true }),
    ).not.toBeVisible()
  })

  test('Escape closes the command palette', async ({ page }) => {
    await page.keyboard.press('Meta+k')

    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).toBeVisible()

    await page.keyboard.press('Escape')

    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).not.toBeVisible()
  })

  test('pressing Cmd+K again toggles palette closed', async ({ page }) => {
    await page.keyboard.press('Meta+k')
    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).toBeVisible()

    await page.keyboard.press('Meta+k')
    await expect(
      page.getByRole('dialog', { name: /command palette/i }),
    ).not.toBeVisible()
  })

  test('all navigation items are listed when search is empty', async ({
    page,
  }) => {
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
        dialog.getByRole('option', { name: pageName, exact: true }),
      ).toBeVisible()
    }
  })
})
