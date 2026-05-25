import { type Page, expect } from '@playwright/test'

/** Dismiss the onboarding welcome dialog so it doesn't block tests. */
async function dismissOnboarding(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('blackbeard_onboarding_completed', 'true')
    localStorage.setItem('blackbeard_tour_completed', 'true')
  })
}

export async function login(
  page: Page,
  email = 'admin@blackbeard.sh',
  password = 'Blackbeard1',
) {
  await dismissOnboarding(page)
  await page.goto('/login')
  await page.getByRole('textbox', { name: /email/i }).fill(email)
  await page.locator('input[type="password"]').fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 })
}

export async function loginAndNavigate(
  page: Page,
  path: string,
  email = 'admin@blackbeard.sh',
  password = 'Blackbeard1',
) {
  await login(page, email, password)
  if (!page.url().includes(path)) {
    await page.goto(path)
    await page.waitForLoadState('domcontentloaded')
    await expect(page).not.toHaveURL(/\/login/, { timeout: 10000 })
  }
}
