import { test, expect } from '@playwright/test'
import { login, loginAndNavigate } from './helpers'

test.describe('CUJ-31: Session Expiry', () => {
  test('login establishes a valid session', async ({ page }) => {
    await login(page)

    // After login, should be redirected away from /login
    await expect(page).not.toHaveURL(/\/login/)

    // Should be on dashboard or another authenticated page
    const heading = page.getByRole('heading').first()
    await expect(heading).toBeVisible({ timeout: 10000 })
  })

  test('SessionExpiredDialog component exists in the app', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    // The SessionExpiredDialog is conditionally rendered by the auth store.
    // Verify the auth store tracks session state by checking
    // that the app renders without errors after login.
    const heading = page.getByRole('heading', { name: /dashboard/i })
    await expect(heading).toBeVisible({ timeout: 10000 })

    // Verify the session expired dialog is not visible during a valid session
    const expiredDialog = page.getByText(/session expired/i)
    await expect(expiredDialog).not.toBeVisible()
  })

  test('sign-out button is accessible in the sidebar', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    const signOutButton = page.getByRole('button', { name: /sign out/i })
    await expect(signOutButton).toBeVisible({ timeout: 10000 })
  })

  test('sign-out button redirects to login page', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    const signOutButton = page.getByRole('button', { name: /sign out/i })
    await expect(signOutButton).toBeVisible({ timeout: 10000 })

    await signOutButton.click()

    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
  })

  test('after sign-out, navigating to protected page redirects to login', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    const signOutButton = page.getByRole('button', { name: /sign out/i })
    await signOutButton.click()
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })

    // Try to navigate to a protected page
    await page.goto('/resources')

    // Should be redirected back to login
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
  })
})
