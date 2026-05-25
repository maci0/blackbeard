import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Authentication', () => {
  test('login page renders form elements', async ({ page }) => {
    await page.goto('/login')

    // Login form is the main content, keep page scope for form elements
    await expect(page.locator('h1, h2, h3').filter({ hasText: /sign in to blackbeard/i })).toBeVisible()
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /create one/i })).toBeVisible()
  })

  test('successful login redirects to studio', async ({ page }) => {
    await login(page)

    await expect(page).toHaveURL('/studio')
    await expect(page).toHaveTitle(/studio/i)
  })

  test('user info shows in sidebar after login', async ({ page }) => {
    await login(page)

    // The user section in the sidebar should display the user's email or name
    await expect(page.getByText('e2e@test.com')).toBeVisible()
  })

  test('logout redirects to login page', async ({ page }) => {
    await login(page)

    await page.getByRole('button', { name: /sign out/i }).click()
    await expect(page).toHaveURL('/login')
  })

  test('register page renders form elements', async ({ page }) => {
    await page.goto('/register')

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: /create your account/i }),
    ).toBeVisible()
    await expect(page.getByLabel(/display name/i)).toBeVisible()
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(page.getByRole('button', { name: /create account/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible()
  })

  test('wrong password shows error message', async ({ page }) => {
    await page.goto('/login')

    await page.getByRole('textbox', { name: /email/i }).fill('e2e@test.com')
    await page.locator('input[type="password"]').fill('WrongPassword123!')
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    // Should remain on the login page
    await expect(page).toHaveURL('/login')
  })

  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto('/studio')

    await expect(page).toHaveURL('/login')
  })
})
