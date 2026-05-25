import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test('debug dashboard', async ({ page }) => {
  await loginAndNavigate(page, '/dashboard')
  await page.waitForTimeout(2000)
  const headings = await page.getByRole('heading').allTextContents()
  console.log('All headings:', headings)
  const h1Text = await page.locator('h1').first().textContent()
  console.log('H1 text:', JSON.stringify(h1Text))
  await expect(page.locator('h1')).toContainText('Dashboard')
})
