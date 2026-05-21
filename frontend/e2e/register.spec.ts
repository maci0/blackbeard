import { test, expect } from '@playwright/test'

test.describe('Register page', () => {
  test('page renders with all form fields', async ({ page }) => {
    await page.goto('/register')

    await expect(
      page.getByRole('heading', { name: /create your account/i }),
    ).toBeVisible()
    await expect(page.getByLabel(/display name/i)).toBeVisible()
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible()
    await expect(page.getByLabel(/password/i)).toBeVisible()
    await expect(
      page.getByRole('button', { name: /create account/i }),
    ).toBeVisible()
  })

  test('Sign in link navigates to login', async ({ page }) => {
    await page.goto('/register')

    const signInLink = page.getByRole('link', { name: /sign in/i })
    await expect(signInLink).toBeVisible()

    await signInLink.click()
    await expect(page).toHaveURL('/login')
  })

  test('password requirements hint appears when typing', async ({ page }) => {
    await page.goto('/register')

    const passwordInput = page.getByLabel(/password/i)
    await passwordInput.fill('abc')

    // Should show hint about characters needed
    await expect(page.getByText(/more character/i)).toBeVisible()
  })

  test('password hint disappears when requirement is met', async ({
    page,
  }) => {
    await page.goto('/register')

    const passwordInput = page.getByLabel(/password/i)
    await passwordInput.fill('abcdefgh')

    // The "more characters needed" hint should not be visible
    await expect(page.getByText(/more character/i)).not.toBeVisible()
  })

  test('show/hide password toggle works', async ({ page }) => {
    await page.goto('/register')

    const passwordInput = page.getByLabel(/^password/i)
    await passwordInput.fill('TestPass1!')

    // Initially password is hidden
    await expect(passwordInput).toHaveAttribute('type', 'password')

    // Click show password button
    await page.getByRole('button', { name: /show password/i }).click()

    // Password should now be visible
    await expect(passwordInput).toHaveAttribute('type', 'text')

    // Click hide password button
    await page.getByRole('button', { name: /hide password/i }).click()

    // Password should be hidden again
    await expect(passwordInput).toHaveAttribute('type', 'password')
  })

  test('submitting empty form shows validation error', async ({ page }) => {
    await page.goto('/register')

    await page.getByRole('button', { name: /create account/i }).click()

    // Should show an error alert
    await expect(page.getByRole('alert')).toBeVisible()
  })

  test('page has correct document title', async ({ page }) => {
    await page.goto('/register')
    await expect(page).toHaveTitle(/create account/i)
  })
})
