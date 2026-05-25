import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Users page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/users')
  })

  test('page loads with header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()
    await expect(page.getByText('Manage platform users and access')).toBeVisible()
  })

  test('user table is visible with at least one user', async ({ page }) => {
    const table = page.getByRole('table', { name: /users/i })
    await expect(table).toBeVisible()

    // At least the admin or e2e test user should be present
    const rows = table.getByRole('row')
    // Header row + at least one data row
    await expect(rows).not.toHaveCount(1)
  })

  test('Invite User button exists', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /invite user/i }),
    ).toBeVisible()
  })

  test('Invite User dialog opens', async ({ page }) => {
    await page.getByRole('button', { name: /invite user/i }).click()

    await expect(
      page.getByRole('heading', { name: /invite user/i }),
    ).toBeVisible()
    await expect(page.getByLabel(/email address/i)).toBeVisible()
    await expect(page.getByLabel(/role/i)).toBeVisible()
  })

  test('Invite User dialog can be closed', async ({ page }) => {
    await page.getByRole('button', { name: /invite user/i }).click()

    await expect(
      page.getByRole('heading', { name: /invite user/i }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(
      page.getByRole('heading', { name: /invite user/i }),
    ).not.toBeVisible()
  })

  test('search filter works', async ({ page }) => {
    const searchInput = page.getByLabel(/search users/i)
    await expect(searchInput).toBeVisible()

    await searchInput.fill('e2e')

    // Should show filtered count
    await expect(page.getByRole('status')).toBeVisible()
  })

  test('search clear button resets results', async ({ page }) => {
    const searchInput = page.getByLabel(/search users/i)
    await searchInput.fill('e2e')

    await page.getByRole('button', { name: /clear search/i }).click()

    await expect(searchInput).toHaveValue('')
  })

  test('Refresh button exists', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh users/i })
    await expect(refreshBtn).toBeVisible()
  })

  test('table headers are present', async ({ page }) => {
    const table = page.getByRole('table', { name: /users/i })
    await expect(table.getByRole('columnheader', { name: /email/i })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: /display name/i })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: /role/i })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: /status/i })).toBeVisible()
  })
})
