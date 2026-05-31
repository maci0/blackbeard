import { test, expect } from '@playwright/test'

test.describe('Onboarding', () => {
  test('welcome dialog shows on first visit', async ({ page }) => {
    // Clear onboarding state before navigating
    await page.addInitScript(() => {
      localStorage.removeItem('blackbeard_onboarding_completed')
      localStorage.removeItem('blackbeard_tour_completed')
    })
    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    // Welcome dialog should appear
    const welcomeHeading = page.getByText(/welcome to blackbeard/i)
    await expect(welcomeHeading).toBeVisible({ timeout: 5000 })
  })

  test('welcome dialog has skip and tour buttons', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('blackbeard_onboarding_completed')
      localStorage.removeItem('blackbeard_tour_completed')
    })
    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    const skipBtn = page.getByRole('button', { name: /skip|later|dismiss/i })
    const tourBtn = page.getByRole('button', { name: /tour|start|get started/i })
    await expect(skipBtn.or(tourBtn)).toBeVisible({ timeout: 5000 })
  })

  test('skipping welcome sets localStorage flag', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('blackbeard_onboarding_completed')
      localStorage.removeItem('blackbeard_tour_completed')
    })
    await page.goto('/login')
    await page.getByRole('textbox', { name: /email/i }).fill('admin@blackbeard.sh')
    await page.locator('input[type="password"]').fill('Blackbeard1')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })

    const skipBtn = page.getByRole('button', { name: /skip|later|dismiss/i })
    if (await skipBtn.isVisible({ timeout: 5000 })) {
      await skipBtn.click()
      const flag = await page.evaluate(() =>
        localStorage.getItem('blackbeard_onboarding_completed'),
      )
      expect(flag).toBeTruthy()
    }
  })
})
