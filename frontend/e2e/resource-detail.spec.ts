import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Resource detail page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('navigating to a resource shows detail page', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    // Click the first resource row to navigate to detail
    const firstRow = main.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Should navigate to a resource detail URL
    await expect(page).toHaveURL(/\/resources\/[a-z-]+\/[a-z0-9-]+/)
  })

  test('detail page shows breadcrumb navigation', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const firstRow = main.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Breadcrumb should be visible with Resources link
    const breadcrumb = main.getByRole('navigation', { name: /breadcrumb/i })
    await expect(breadcrumb).toBeVisible()
    await expect(breadcrumb.getByRole('link', { name: 'Resources' })).toBeVisible()
  })

  test('detail page shows Edit and Delete buttons', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const firstRow = main.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    await expect(
      main.getByRole('button', { name: /edit/i }),
    ).toBeVisible()
    await expect(
      main.getByRole('button', { name: /delete/i }),
    ).toBeVisible()
  })

  test('detail page shows spec fields', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const firstRow = main.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Spec tab should be active by default and show some content
    await expect(main.getByRole('tab', { name: /spec/i })).toBeVisible()
    await expect(main.getByRole('tab', { name: /yaml/i })).toBeVisible()
  })

  test('back navigation from detail page works', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const firstRow = main.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Click Resources link in breadcrumb to go back
    const breadcrumb = main.getByRole('navigation', { name: /breadcrumb/i })
    await breadcrumb.getByRole('link', { name: 'Resources' }).click()

    await expect(page).toHaveURL('/resources')
  })

  test('detail page shows metadata strip', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const firstRow = main.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // API Version should always be present in the metadata strip
    await expect(main.getByText(/api version/i)).toBeVisible()
    await expect(main.getByText(/updated/i)).toBeVisible()
  })

  test('Edit button switches to YAML editing mode', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const firstRow = main.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    await main.getByRole('button', { name: /edit/i }).click()

    // In edit mode, Cancel and Save buttons should appear
    await expect(main.getByRole('button', { name: /cancel/i })).toBeVisible()
    await expect(main.getByRole('button', { name: /save/i })).toBeVisible()
  })
})
