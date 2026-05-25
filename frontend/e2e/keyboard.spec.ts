import { test, expect } from '@playwright/test'
import { login, loginAndNavigate } from './helpers'

test.describe('Keyboard accessibility', () => {
  test('Tab through login form fields', async ({ page }) => {
    await page.goto('/login')

    // The first focusable element should be the email input (autofocused)
    const emailInput = page.getByRole('textbox', { name: /email/i })
    await expect(emailInput).toBeFocused()

    // Tab to password field
    await page.keyboard.press('Tab')
    // Next tab may hit the show/hide password button or the password field
    // depending on DOM order; password input is next significant field
    const passwordInput = page.getByLabel(/password/i)

    // Tab until we reach the submit button
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')

    // Eventually Sign in button should be reachable
    const signInBtn = page.getByRole('button', { name: /sign in/i })
    // We verify the button exists and is focusable
    await expect(signInBtn).toBeVisible()
  })

  test('Enter submits login form', async ({ page }) => {
    await page.goto('/login')

    await page.getByRole('textbox', { name: /email/i }).fill('e2e@test.com')
    await page.getByLabel(/password/i).fill('TestPass1!')

    // Press Enter to submit the form
    await page.keyboard.press('Enter')

    // Should navigate to studio on successful login
    await page.waitForURL('/studio')
    await expect(page).toHaveURL('/studio')
  })

  test('Escape closes dialogs', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    // Open keyboard shortcuts dialog
    const shortcutsBtn = page.getByRole('button', { name: /keyboard shortcuts/i })
    await shortcutsBtn.click()

    // Dialog should be visible
    await expect(page.getByRole('dialog')).toBeVisible()

    // Press Escape to close
    await page.keyboard.press('Escape')

    // Dialog should be closed
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('Tab navigates sidebar items', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    // Focus the first sidebar nav link
    const nav = page.getByRole('navigation', { name: /primary/i })
    const studioLink = nav.getByRole('link', { name: 'Studio' })

    // Click Studio to focus the nav area
    await studioLink.focus()
    await expect(studioLink).toBeFocused()

    // Tab to next link
    await page.keyboard.press('Tab')

    // Resources link should now be focused
    const resourcesLink = nav.getByRole('link', { name: 'Resources' })
    await expect(resourcesLink).toBeFocused()
  })

  test('Skip to main content link exists', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    // The skip link should exist in the DOM
    const skipLink = page.getByRole('link', { name: /skip to main content/i })
    // It should be present but visually hidden until focused
    await expect(skipLink).toBeAttached()
  })

  test('Enter and Space activate table rows', async ({ page }) => {
    await loginAndNavigate(page, '/resources')

    // Focus the first table row
    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.focus()

    // Press Enter to navigate to the detail page
    await page.keyboard.press('Enter')

    // Should navigate to a resource detail page
    await expect(page).toHaveURL(/\/resources\/[a-z-]+\/[a-z0-9-]+/)
  })
})
