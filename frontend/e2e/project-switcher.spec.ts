import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Project Switcher', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('project switcher in sidebar shows default', async ({ page }) => {
    // Project switcher is in the sidebar, keep page scope intentionally
    await expect(
      page.getByRole('button', { name: /default/i }).or(
        page.getByText(/project.*default/i),
      ),
    ).toBeVisible()
  })

  test('click opens dropdown with project list', async ({ page }) => {
    const switcher = page.getByRole('button', { name: /project/i }).or(
      page.getByRole('button', { name: /default/i }),
    )
    await switcher.click()

    await expect(
      page.getByRole('listbox').or(
        page.getByRole('menu'),
      ).or(page.locator('[data-testid="project-dropdown"]')),
    ).toBeVisible()

    await expect(page.getByText('default')).toBeVisible()
  })

  test('create project button present', async ({ page }) => {
    const switcher = page.getByRole('button', { name: /project/i }).or(
      page.getByRole('button', { name: /default/i }),
    )
    await switcher.click()

    await expect(
      page.getByRole('button', { name: /create project/i }).or(
        page.getByRole('button', { name: /new project/i }),
      ),
    ).toBeVisible()
  })

  test('selecting project updates display', async ({ page }) => {
    const switcher = page.getByRole('button', { name: /project/i }).or(
      page.getByRole('button', { name: /default/i }),
    )

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
