import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Roles page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/roles')
  })

  test('displays role cards', async ({ page }) => {
    const main = page.locator('main')
    // Wait for roles to load: expect at least one role button
    const roleCards = main.getByRole('button', { name: /^role:/i })
    await expect(roleCards.first()).toBeVisible()

    // Verify we have the expected number of roles from seed data
    await expect(roleCards).toHaveCount(9)
  })

  test('shows expected role names', async ({ page }) => {
    const main = page.locator('main')
    const expectedRoles = [
      'admin',
      'developer',
      'operator',
      'viewer',
      'owner',
    ]

    for (const roleName of expectedRoles) {
      await expect(main.getByText(roleName, { exact: true }).first()).toBeVisible()
    }
  })

  test('create role button opens dialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /create role/i }).first().click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: /create role/i }),
    ).toBeVisible()
    await expect(page.getByLabel(/^name/i)).toBeVisible()
    await expect(page.getByLabel(/description/i)).toBeVisible()
    await expect(
      page.getByText('Define a role with permissions for platform resources.'),
    ).toBeVisible()
  })

  test('create role dialog can be closed', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /create role/i }).first().click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: /create role/i }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: /create role/i }),
    ).not.toBeVisible()
  })

  test('page header shows title and description', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Roles' })).toBeVisible()
    await expect(
      main.getByText('Access control roles and permissions'),
    ).toBeVisible()
  })
})
