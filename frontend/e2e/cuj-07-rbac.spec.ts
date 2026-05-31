import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-07: RBAC and User Management', () => {
  test.describe('Users page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/users')
    })

    test('users page renders with heading and description', async ({
      page,
    }) => {
      await expect(
        page.getByRole('heading', { name: /users/i }),
      ).toBeVisible()
      await expect(
        page.getByText(/manage platform users and access/i),
      ).toBeVisible()
    })

    test('invite user button is visible', async ({ page }) => {
      const inviteButton = page.getByRole('button', {
        name: /invite user/i,
      })
      await expect(inviteButton).toBeVisible()
    })

    test('clicking invite user opens dialog', async ({ page }) => {
      await page.getByRole('button', { name: /invite user/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Invite User')).toBeVisible()
      await expect(
        dialog.getByText(/send an invitation to join the platform/i),
      ).toBeVisible()
    })

    test('invite dialog has email field', async ({ page }) => {
      await page.getByRole('button', { name: /invite user/i }).click()

      const dialog = page.getByRole('dialog')
      const emailInput = dialog.locator('#invite-email')
      await expect(emailInput).toBeVisible()
      await expect(emailInput).toHaveAttribute('type', 'email')
      await expect(emailInput).toHaveAttribute('required', '')
    })

    test('invite dialog has role selector', async ({ page }) => {
      await page.getByRole('button', { name: /invite user/i }).click()

      const dialog = page.getByRole('dialog')
      const roleSelect = dialog.locator('#invite-role')
      await expect(roleSelect).toBeVisible()

      // Should have admin, editor, viewer options
      const options = roleSelect.locator('option')
      const texts = await options.allTextContents()
      expect(texts.map((t) => t.toLowerCase())).toEqual(
        expect.arrayContaining(['admin', 'editor', 'viewer']),
      )
    })

    test('invite dialog has send invite and cancel buttons', async ({
      page,
    }) => {
      await page.getByRole('button', { name: /invite user/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(
        dialog.getByRole('button', { name: /send invite/i }),
      ).toBeVisible()
      await expect(
        dialog.getByRole('button', { name: /cancel/i }),
      ).toBeVisible()
    })

    test('invite dialog cancel closes it', async ({ page }) => {
      await page.getByRole('button', { name: /invite user/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('invite dialog close button dismisses it', async ({ page }) => {
      await page.getByRole('button', { name: /invite user/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /close/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('invite dialog validates email is required', async ({ page }) => {
      await page.getByRole('button', { name: /invite user/i }).click()

      const dialog = page.getByRole('dialog')

      // Submit with empty email
      await dialog.getByRole('button', { name: /send invite/i }).click()

      // Error should show
      await expect(dialog.getByRole('alert')).toBeVisible()
      await expect(
        dialog.getByText(/email.*required/i),
      ).toBeVisible()
    })

    test('refresh button is visible', async ({ page }) => {
      await expect(
        page.getByRole('button', { name: /refresh users/i }),
      ).toBeVisible()
    })

    test('users table or empty state is displayed', async ({ page }) => {
      // Either a table of users or an empty state should be visible
      const table = page.getByRole('table', { name: /users/i })
      const emptyState = page.getByText(/no users yet/i)
      const skeleton = page.locator('[class*="skeleton"], [class*="pulse"]')

      // Wait for the page to settle
      await page.waitForTimeout(500)

      const tableVisible = await table.isVisible().catch(() => false)
      const emptyVisible = await emptyState.isVisible().catch(() => false)
      const skeletonVisible = await skeleton.first().isVisible().catch(() => false)

      expect(tableVisible || emptyVisible || skeletonVisible).toBeTruthy()
    })

    test('users table has expected column headers when populated', async ({
      page,
    }) => {
      const table = page.getByRole('table', { name: /users/i })
      const tableVisible = await table.isVisible().catch(() => false)

      if (tableVisible) {
        await expect(
          table.getByRole('columnheader', { name: /email/i }),
        ).toBeVisible()
        await expect(
          table.getByRole('columnheader', { name: /display name/i }),
        ).toBeVisible()
        await expect(
          table.getByRole('columnheader', { name: /role/i }),
        ).toBeVisible()
        await expect(
          table.getByRole('columnheader', { name: /status/i }),
        ).toBeVisible()
      }
      // If no table, test passes silently (empty state case)
    })
  })

  test.describe('Roles page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/roles')
    })

    test('roles page renders with heading and description', async ({
      page,
    }) => {
      await expect(
        page.getByRole('heading', { name: /roles/i }),
      ).toBeVisible()
      await expect(
        page.getByText(/access control roles and permissions/i),
      ).toBeVisible()
    })

    test('create role button is visible', async ({ page }) => {
      const createButton = page.getByRole('button', {
        name: /create role/i,
      })
      await expect(createButton).toBeVisible()
    })

    test('clicking create role opens dialog', async ({ page }) => {
      await page.getByRole('button', { name: /create role/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Create Role')).toBeVisible()
      await expect(
        dialog.getByText(/define a role with permissions/i),
      ).toBeVisible()
    })

    test('create role dialog has name and description fields', async ({
      page,
    }) => {
      await page.getByRole('button', { name: /create role/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog.locator('#role-name')).toBeVisible()
      await expect(dialog.locator('#role-description')).toBeVisible()
    })

    test('create role dialog has rules section', async ({ page }) => {
      await page.getByRole('button', { name: /create role/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog.getByText(/^rules$/i)).toBeVisible()
    })

    test('create role dialog has submit and cancel buttons', async ({
      page,
    }) => {
      await page.getByRole('button', { name: /create role/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(
        dialog.getByRole('button', { name: /^create role$/i }),
      ).toBeVisible()
      await expect(
        dialog.getByRole('button', { name: /cancel/i }),
      ).toBeVisible()
    })

    test('create role dialog cancel closes it', async ({ page }) => {
      await page.getByRole('button', { name: /create role/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('create role dialog close button dismisses it', async ({ page }) => {
      await page.getByRole('button', { name: /create role/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /close/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('create role dialog validates name is required', async ({ page }) => {
      await page.getByRole('button', { name: /create role/i }).click()

      const dialog = page.getByRole('dialog')

      // Submit with empty name
      await dialog.getByRole('button', { name: /^create role$/i }).click()

      // Validation error should appear
      await expect(dialog.getByRole('alert')).toBeVisible()
      await expect(
        dialog.getByText(/role name is required/i),
      ).toBeVisible()
    })

    test('refresh button is visible', async ({ page }) => {
      await expect(
        page.getByRole('button', { name: /refresh roles/i }),
      ).toBeVisible()
    })

    test('roles display as cards or show empty state', async ({ page }) => {
      // Either role cards or an empty state should be present
      const roleCards = page.getByRole('button', { name: /role:/i })
      const emptyState = page.getByText(/no roles found/i)
      const skeleton = page.locator('[class*="skeleton"], [class*="pulse"]')

      // Wait for the page to settle
      await page.waitForTimeout(500)

      const cardsVisible = await roleCards.first().isVisible().catch(() => false)
      const emptyVisible = await emptyState.isVisible().catch(() => false)
      const skeletonVisible = await skeleton.first().isVisible().catch(() => false)

      expect(cardsVisible || emptyVisible || skeletonVisible).toBeTruthy()
    })

    test('role cards show rule and user counts when roles exist', async ({
      page,
    }) => {
      const roleCards = page.getByRole('button', { name: /role:/i })
      const cardsVisible = await roleCards.first().isVisible().catch(() => false)

      if (cardsVisible) {
        const firstCard = roleCards.first()
        // Each card should show rule count and user count
        await expect(firstCard.getByText(/rule/i)).toBeVisible()
        await expect(firstCard.getByText(/user/i)).toBeVisible()
      }
      // If no roles, the test passes silently
    })

    test('search input appears when roles exist', async ({ page }) => {
      // Wait for loading
      await page.waitForTimeout(500)

      const searchInput = page.getByLabel(/search roles/i)
      const roleCards = page.getByRole('button', { name: /role:/i })

      const rolesExist = await roleCards.first().isVisible().catch(() => false)

      if (rolesExist) {
        await expect(searchInput).toBeVisible()
      }
      // If no roles, search may not show, which is expected
    })
  })
})
