import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Collaboration', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('collaboration toggle exists in toolbar', async ({ page }) => {
    // Studio page should be loaded after login
    const collabBtn = page.getByRole('button', {
      name: /collab|collaboration/i,
    })
    await expect(collabBtn).toBeVisible()
  })

  test('collaboration button can be toggled', async ({ page }) => {
    const collabBtn = page.getByRole('button', {
      name: /enable live collaboration/i,
    })
    await expect(collabBtn).toBeVisible()
    // Button should have aria-pressed="false" initially
    await expect(collabBtn).toHaveAttribute('aria-pressed', 'false')
    // Click to enable
    await collabBtn.click()
    // After clicking, it should change to pressed state
    await expect(collabBtn).toHaveAttribute('aria-pressed', 'true')
  })
})
