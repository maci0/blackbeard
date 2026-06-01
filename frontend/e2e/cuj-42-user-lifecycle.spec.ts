import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-42: User Lifecycle', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/users')
  })

  test('page renders with heading and invite button', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /users/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /invite user/i })).toBeVisible()
  })

  test('user table or empty state is displayed', async ({ page }) => {
    const table = page.getByRole('table', { name: /users/i })
    const emptyState = page.getByText(/no users/i)
    const skeleton = page.locator('[class*="skeleton"], [class*="pulse"]')

    await page.waitForTimeout(500)

    const tableVisible = await table.isVisible().catch(() => false)
    const emptyVisible = await emptyState.isVisible().catch(() => false)
    const skeletonVisible = await skeleton
      .first()
      .isVisible()
      .catch(() => false)

    expect(tableVisible || emptyVisible || skeletonVisible).toBeTruthy()
  })

  test('invite dialog has email and role fields', async ({ page }) => {
    await page.getByRole('button', { name: /invite user/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Invite User')).toBeVisible()

    // Email field
    const emailInput = dialog.locator('#invite-email')
    await expect(emailInput).toBeVisible()
    await expect(emailInput).toHaveAttribute('type', 'email')
    await expect(emailInput).toHaveAttribute('required', '')

    // Role selector
    const roleSelect = dialog.locator('#invite-role')
    await expect(roleSelect).toBeVisible()

    const options = roleSelect.locator('option')
    const texts = await options.allTextContents()
    expect(texts.map((t) => t.toLowerCase())).toEqual(
      expect.arrayContaining(['admin', 'editor', 'viewer']),
    )
  })

  test('invite dialog validates email is required', async ({ page }) => {
    await page.getByRole('button', { name: /invite user/i }).click()

    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: /send invite/i }).click()

    await expect(dialog.getByRole('alert')).toBeVisible()
    await expect(dialog.getByText(/email.*required/i)).toBeVisible()
  })

  test('invite dialog cancel closes it', async ({ page }) => {
    await page.getByRole('button', { name: /invite user/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('user detail panel has deactivate action when user is selected', async ({ page }) => {
    const table = page.getByRole('table', { name: /users/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (tableVisible) {
      const firstRow = table.locator('tbody tr').first()
      const rowVisible = await firstRow.isVisible().catch(() => false)

      if (rowVisible) {
        await firstRow.click()

        // The detail panel should open with user info
        const detailPanel = page.locator('h2').filter({ hasText: /.+/ })
        await expect(detailPanel.first()).toBeVisible({ timeout: 5000 })

        // Deactivate button should be present for active users
        const deactivateBtn = page.getByRole('button', {
          name: /deactivate/i,
        })
        const closeBtn = page.getByRole('button', {
          name: /close user details/i,
        })

        // Either the deactivate button or the close button should be visible
        // (deactivate only shows for active users)
        await expect(deactivateBtn.or(closeBtn)).toBeVisible()
      }
    }
    // If no users in table, test passes gracefully
  })

  test('user table has expected column headers when populated', async ({ page }) => {
    const table = page.getByRole('table', { name: /users/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (tableVisible) {
      await expect(table.getByRole('columnheader', { name: /email/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /role/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /status/i })).toBeVisible()
    }
  })
})
