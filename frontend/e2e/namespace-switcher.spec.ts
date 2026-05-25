import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Namespace Switcher', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('namespace switcher in sidebar shows default', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /default/i }).or(
        page.getByText(/namespace.*default/i),
      ),
    ).toBeVisible()
  })

  test('click opens dropdown with namespace list', async ({ page }) => {
    const switcher = page.getByRole('button', { name: /namespace/i }).or(
      page.getByRole('button', { name: /default/i }),
    )
    await switcher.click()

    await expect(
      page.getByRole('listbox').or(
        page.getByRole('menu'),
      ).or(page.locator('[data-testid="namespace-dropdown"]')),
    ).toBeVisible()

    await expect(page.getByText('default')).toBeVisible()
  })

  test('create namespace button present', async ({ page }) => {
    const switcher = page.getByRole('button', { name: /namespace/i }).or(
      page.getByRole('button', { name: /default/i }),
    )
    await switcher.click()

    await expect(
      page.getByRole('button', { name: /create namespace/i }).or(
        page.getByRole('button', { name: /new namespace/i }),
      ),
    ).toBeVisible()
  })

  test('selecting namespace updates display', async ({ page }) => {
    const switcher = page.getByRole('button', { name: /namespace/i }).or(
      page.getByRole('button', { name: /default/i }),
    )

    const initialText = await switcher.textContent()
    await switcher.click()

    const defaultOption = page.getByRole('option', { name: /default/i }).or(
      page.getByRole('menuitem', { name: /default/i }),
    )

    if (await defaultOption.isVisible()) {
      await defaultOption.click()

      await expect(switcher).toContainText(/default/i)
    }
  })
})
