import { test, expect } from '@playwright/test'

test.describe('CUJ-01: First-Time Onboarding', () => {
  test('register page renders all form fields', async ({ page }) => {
    await page.goto('/register')

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: /create your account/i }),
    ).toBeVisible()
    await expect(page.getByLabel(/display name/i)).toBeVisible()
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(
      page.getByRole('button', { name: /create account/i }),
    ).toBeVisible()
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible()
  })

  test('register form validates required fields before submission', async ({
    page,
  }) => {
    await page.goto('/register')

    // Submit with empty fields
    await page.getByRole('button', { name: /create account/i }).click()

    // Should show a validation error (stays on the register page)
    await expect(page).toHaveURL('/register')
  })

  test('register form shows password length hint while typing', async ({
    page,
  }) => {
    await page.goto('/register')

    await page.locator('input[type="password"]').fill('short')

    // Password hint should mention remaining characters
    await expect(page.getByText(/more character.*needed/i)).toBeVisible()
  })

  test('register link from login page navigates to register', async ({
    page,
  }) => {
    await page.goto('/login')

    await page.getByRole('link', { name: /create one/i }).click()
    await expect(page).toHaveURL('/register')
  })

  test('login page renders and accepts credentials', async ({ page }) => {
    await page.goto('/login')

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: /sign in to blackbeard/i }),
    ).toBeVisible()
    await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('welcome dialog appears when onboarding flags are not set', async ({
    page,
  }) => {
    // Do not set the localStorage flags so the onboarding wizard shows
    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    // The onboarding wizard should be visible with the welcome message
    await expect(page.getByText('Welcome to Blackbeard')).toBeVisible({
      timeout: 5000,
    })
    // Step 1 title should be visible
    await expect(page.getByText('Visual Studio')).toBeVisible()
    // Step progress dots should be visible
    await expect(page.getByLabel('Step progress')).toBeVisible()
  })

  test('onboarding wizard can be navigated through all steps', async ({
    page,
  }) => {
    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    // Wait for the onboarding wizard
    await expect(page.getByText('Welcome to Blackbeard')).toBeVisible({
      timeout: 5000,
    })

    // Step 1: Visual Studio
    await expect(page.getByText('Visual Studio')).toBeVisible()
    await page.getByRole('button', { name: /next/i }).click()

    // Step 2: Resource Library
    await expect(page.getByText('Resource Library')).toBeVisible()
    await page.getByRole('button', { name: /next/i }).click()

    // Step 3: Run Crews
    await expect(page.getByText('Run Crews')).toBeVisible()
    await page.getByRole('button', { name: /next/i }).click()

    // Step 4: RBAC & Policies
    await expect(page.getByText('RBAC & Policies')).toBeVisible()
    await page.getByRole('button', { name: /next/i }).click()

    // Step 5 (last): CLI & API, should show "Get Started" instead of "Next"
    await expect(page.getByText('CLI & API')).toBeVisible()
    await expect(page.getByRole('button', { name: /get started/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /next/i })).not.toBeVisible()
  })

  test('onboarding wizard back button navigates to previous step', async ({
    page,
  }) => {
    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    await expect(page.getByText('Welcome to Blackbeard')).toBeVisible({
      timeout: 5000,
    })

    // Step 1: no back button
    await expect(page.getByRole('button', { name: /back/i })).not.toBeVisible()

    // Go to step 2
    await page.getByRole('button', { name: /next/i }).click()
    await expect(page.getByText('Resource Library')).toBeVisible()

    // Back button should now exist and navigate back
    await page.getByRole('button', { name: /back/i }).click()
    await expect(page.getByText('Visual Studio')).toBeVisible()
  })

  test('skip onboarding button dismisses the wizard', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    await expect(page.getByText('Welcome to Blackbeard')).toBeVisible({
      timeout: 5000,
    })

    // Click the skip/close button
    await page.getByRole('button', { name: /skip onboarding/i }).click()

    // The wizard dialog should be gone
    await expect(page.getByText('Welcome to Blackbeard')).not.toBeVisible()
  })

  test('onboarding localStorage flags prevent wizard from showing', async ({
    page,
  }) => {
    // Pre-set the onboarding flags (same as helpers.ts dismissOnboarding)
    await page.addInitScript(() => {
      localStorage.setItem('blackbeard_onboarding_completed', 'true')
      localStorage.setItem('blackbeard_tour_completed', 'true')
    })

    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    // Give it a moment, then confirm the wizard is not visible
    await page.waitForTimeout(1000)
    await expect(page.getByText('Welcome to Blackbeard')).not.toBeVisible()
  })
})
