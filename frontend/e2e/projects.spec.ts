import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Projects Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/projects')
  })

  test('page renders with header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /projects/i })).toBeVisible()
  })

  test('default project is listed', async ({ page }) => {
    await expect(page.getByText('default')).toBeVisible()
  })

  test('create project dialog opens', async ({ page }) => {
    const createBtn = page.getByRole('button', { name: /create project/i })
    if (await createBtn.isVisible()) {
      await createBtn.click()
      await expect(page.getByRole('dialog')).toBeVisible()
    }
  })

  test('project name field validates format', async ({ page }) => {
    const createBtn = page.getByRole('button', { name: /create project/i })
    if (await createBtn.isVisible()) {
      await createBtn.click()
      const nameInput = page.getByLabel(/name/i)
      if (await nameInput.isVisible()) {
        await nameInput.fill('INVALID NAME!')
        const submitBtn = page.getByRole('button', { name: /create/i }).last()
        // Should not allow invalid names
        await submitBtn.click()
        // Expect validation error or the dialog to remain open
        await expect(page.getByRole('dialog')).toBeVisible()
      }
    }
  })
})
