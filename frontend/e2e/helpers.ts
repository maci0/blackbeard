import { type Page } from '@playwright/test'

export async function login(
  page: Page,
  email = 'e2e@test.com',
  password = 'TestPass1!',
) {
  await page.goto('/login')
  await page.getByRole('textbox', { name: /email/i }).fill(email)
  // Password fields have role 'textbox' when using getByLabel; use the label selector instead
  await page.getByLabel(/password/i).fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL('/studio')
}
