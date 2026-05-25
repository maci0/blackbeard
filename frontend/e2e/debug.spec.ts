import { test } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test('debug dashboard', async ({ page }) => {
  await loginAndNavigate(page, '/dashboard')
  await page.waitForTimeout(3000)
  await page.screenshot({ path: 'debug-dashboard.png' })
  console.log('URL:', page.url())
})
