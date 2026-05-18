import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Roles page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: 'Roles' }).click()
    await page.waitForURL('/roles')
  })

  test('displays role cards', async ({ page }) => {
    // Wait for roles to load — expect at least one role button
    const roleCards = page.getByRole('button', { name: /^role:/i })
    await expect(roleCards.first()).toBeVisible()

    // Verify we have the expected number of roles from seed data
    await expect(roleCards).toHaveCount(9)
  })

  test('shows expected role names', async ({ page }) => {
    const expectedRoles = [
      'admin',
      'developer',
      'operator',
      'viewer',
      'owner',
    ]

    for (const roleName of expectedRoles) {
      await expect(page.getByText(roleName, { exact: true }).first()).toBeVisible()
    }
  })

  test('create role button opens dialog', async ({ page }) => {
    await page.getByRole('button', { name: /create role/i }).first().click()

    await expect(
      page.getByRole('heading', { name: /create role/i }),
    ).toBeVisible()
    await expect(page.getByLabel(/^name/i)).toBeVisible()
    await expect(page.getByLabel(/description/i)).toBeVisible()
    await expect(
      page.getByText('Define a role with permissions for platform resources.'),
    ).toBeVisible()
  })

  test('create role dialog can be closed', async ({ page }) => {
    await page.getByRole('button', { name: /create role/i }).first().click()

    await expect(
      page.getByRole('heading', { name: /create role/i }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(
      page.getByRole('heading', { name: /create role/i }),
    ).not.toBeVisible()
  })

  test('page header shows title and description', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Roles' })).toBeVisible()
    await expect(
      page.getByText('Access control roles and permissions'),
    ).toBeVisible()
  })
})
