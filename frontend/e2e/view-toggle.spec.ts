import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('View toggle', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Models page has view toggle', async ({ page }) => {
    await page.goto('/models')

    const viewToggle = page.getByRole('radiogroup', { name: /view mode/i })
    await expect(viewToggle).toBeVisible()

    await expect(
      viewToggle.getByRole('radio', { name: /card view/i }),
    ).toBeVisible()
    await expect(
      viewToggle.getByRole('radio', { name: /list view/i }),
    ).toBeVisible()
  })

  test('toggle switches between card and list views on Models', async ({
    page,
  }) => {
    await page.goto('/models')

    const viewToggle = page.getByRole('radiogroup', { name: /view mode/i })
    const cardRadio = viewToggle.getByRole('radio', { name: /card view/i })
    const listRadio = viewToggle.getByRole('radio', { name: /list view/i })

    await listRadio.click()
    await expect(listRadio).toHaveAttribute('aria-checked', 'true')
    await expect(cardRadio).toHaveAttribute('aria-checked', 'false')

    await cardRadio.click()
    await expect(cardRadio).toHaveAttribute('aria-checked', 'true')
    await expect(listRadio).toHaveAttribute('aria-checked', 'false')
  })

  test('Resources page has view toggle', async ({ page }) => {
    await page.goto('/resources')

    const viewToggle = page.getByRole('radiogroup', { name: /view mode/i })
    await expect(viewToggle).toBeVisible()
  })

  test('view preference persists after reload', async ({ page }) => {
    await page.goto('/models')

    const viewToggle = page.getByRole('radiogroup', { name: /view mode/i })
    const listRadio = viewToggle.getByRole('radio', { name: /list view/i })

    await listRadio.click()
    await expect(listRadio).toHaveAttribute('aria-checked', 'true')

    await page.reload()

    const reloadedToggle = page.getByRole('radiogroup', {
      name: /view mode/i,
    })
    const reloadedListRadio = reloadedToggle.getByRole('radio', {
      name: /list view/i,
    })
    await expect(reloadedListRadio).toHaveAttribute('aria-checked', 'true')
  })
})
