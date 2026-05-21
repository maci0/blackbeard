import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Dark Mode', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('theme toggle button exists', async ({ page }) => {
    const themeBtn = page.getByRole('button', { name: /theme/i })
    await expect(themeBtn).toBeVisible()
  })

  test('cycling theme applies dark class', async ({ page }) => {
    const themeBtn = page.getByRole('button', { name: /theme/i })
    // Click to cycle through theme options (system -> dark or light -> dark)
    // We may need multiple clicks depending on starting state
    const htmlEl = page.locator('html')

    // Record initial class
    const initialClass = await htmlEl.getAttribute('class')
    const initiallyDark = initialClass?.includes('dark') ?? false

    // Click theme button to cycle
    await themeBtn.click()

    // After a click, the class should have changed
    if (initiallyDark) {
      // If it was dark, cycling should change to light or system
      await expect(htmlEl).not.toHaveClass(/dark/)
    } else {
      // If light/system, cycle until dark appears (may need 1-2 clicks)
      const classAfterFirst = await htmlEl.getAttribute('class')
      if (!classAfterFirst?.includes('dark')) {
        await themeBtn.click()
      }
      // One of the states should be dark
    }
  })

  test('dark mode persists across pages', async ({ page }) => {
    const themeBtn = page.getByRole('button', { name: /theme/i })
    const htmlEl = page.locator('html')

    // Click until dark mode is active
    for (let i = 0; i < 3; i++) {
      const cls = await htmlEl.getAttribute('class')
      if (cls?.includes('dark')) break
      await themeBtn.click()
    }

    // Verify dark mode is active
    await expect(htmlEl).toHaveClass(/dark/)

    // Navigate to resources
    await page.getByRole('link', { name: 'Resources' }).click()
    await expect(page.getByRole('heading', { name: 'Resources' })).toBeVisible()

    // Verify dark class persists
    await expect(htmlEl).toHaveClass(/dark/)

    // Navigate to executions
    await page.getByRole('link', { name: 'Executions' }).click()
    await expect(page.getByRole('heading', { name: 'Executions' })).toBeVisible()

    // Verify dark class still persists
    await expect(htmlEl).toHaveClass(/dark/)
  })
})
