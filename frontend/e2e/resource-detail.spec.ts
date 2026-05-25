import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Resource detail page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('navigating to a resource shows detail page', async ({ page }) => {
    await page.goto('/resources')

    // Click the first resource row to navigate to detail
    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Should navigate to a resource detail URL
    await expect(page).toHaveURL(/\/resources\/[a-z-]+\/[a-z0-9-]+/)
  })

  test('detail page shows breadcrumb navigation', async ({ page }) => {
    await page.goto('/resources')

    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Breadcrumb should be visible with Resources link
    const breadcrumb = page.getByRole('navigation', { name: /breadcrumb/i })
    await expect(breadcrumb).toBeVisible()
    await expect(breadcrumb.getByRole('link', { name: 'Resources' })).toBeVisible()
  })

  test('detail page shows Edit and Delete buttons', async ({ page }) => {
    await page.goto('/resources')

    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    await expect(
      page.getByRole('button', { name: /edit/i }),
    ).toBeVisible()
    await expect(
      page.getByRole('button', { name: /delete/i }),
    ).toBeVisible()
  })

  test('detail page shows spec fields', async ({ page }) => {
    await page.goto('/resources')

    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Spec tab should be active by default and show some content
    await expect(page.getByRole('tab', { name: /spec/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /yaml/i })).toBeVisible()
  })

  test('back navigation from detail page works', async ({ page }) => {
    await page.goto('/resources')

    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // Click Resources link in breadcrumb to go back
    const breadcrumb = page.getByRole('navigation', { name: /breadcrumb/i })
    await breadcrumb.getByRole('link', { name: 'Resources' }).click()

    await expect(page).toHaveURL('/resources')
  })

  test('detail page shows metadata strip', async ({ page }) => {
    await page.goto('/resources')

    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    // API Version should always be present in the metadata strip
    await expect(page.getByText(/api version/i)).toBeVisible()
    await expect(page.getByText(/updated/i)).toBeVisible()
  })

  test('Edit button switches to YAML editing mode', async ({ page }) => {
    await page.goto('/resources')

    const firstRow = page.getByRole('row', { name: /press enter to view details/i }).first()
    await firstRow.click()

    await page.getByRole('button', { name: /edit/i }).click()

    // In edit mode, Cancel and Save buttons should appear
    await expect(page.getByRole('button', { name: /cancel/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /save/i })).toBeVisible()
  })
})
