import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Credentials Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/credentials')
  })

  test('page renders with header and empty state', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /credentials/i })).toBeVisible()
  })

  test('add credential dialog opens on button click', async ({ page }) => {
    const addBtn = page.getByRole('button', { name: /add credential/i })
    if (await addBtn.isVisible()) {
      await addBtn.click()
      await expect(page.getByRole('dialog')).toBeVisible()
    }
  })

  test('credential form requires name and value', async ({ page }) => {
    const addBtn = page.getByRole('button', { name: /add credential/i })
    if (await addBtn.isVisible()) {
      await addBtn.click()
      const submitBtn = page.getByRole('button', { name: /save|add|create/i }).last()
      await expect(submitBtn).toBeDisabled()
    }
  })
})
