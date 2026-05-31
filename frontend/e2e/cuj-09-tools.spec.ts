import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-09: Tool Management', () => {
  test.describe('Tools page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/tools')
    })

    test('page renders with heading and action buttons', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /^tools$/i })).toBeVisible()
      await expect(page.getByText(/tool library and registry/i)).toBeVisible()

      // Action buttons in header
      await expect(page.getByRole('button', { name: /refresh/i })).toBeVisible()
      await expect(page.getByRole('link', { name: /browse library/i })).toBeVisible()
      await expect(page.getByRole('link', { name: /create in studio/i })).toBeVisible()
    })

    test('browse library link navigates to /tools/library', async ({ page }) => {
      await page.getByRole('link', { name: /browse library/i }).click()
      await expect(page).toHaveURL(/\/tools\/library/)
    })

    test('shows empty state or tool cards', async ({ page }) => {
      // Either tool cards are rendered or the empty state is shown
      const emptyState = page.getByText(/no tools yet/i)
      const toolGrid = page.locator('.grid')

      await expect(emptyState.or(toolGrid)).toBeVisible()
    })
  })

  test.describe('Tools Library page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/tools/library')
    })

    test('page renders with heading', async ({ page }) => {
      await expect(
        page.getByRole('heading', { name: /tools library/i }),
      ).toBeVisible()
      await expect(
        page.getByText(/browse and install curated tools/i),
      ).toBeVisible()
    })

    test('search input is visible and functional', async ({ page }) => {
      const searchInput = page.getByRole('searchbox', {
        name: /search tools library/i,
      })
      await expect(searchInput).toBeVisible()

      // Type a search query
      await searchInput.fill('web')
      // Page should still render (either filtered results or "no tools match")
      await expect(
        page.locator('.grid').or(page.getByText(/no tools match/i)),
      ).toBeVisible()
    })

    test('category filter chips are rendered', async ({ page }) => {
      // The "All" chip should always be present
      await expect(page.getByRole('button', { name: 'All' })).toBeVisible()
    })

    test('tool cards show install buttons', async ({ page }) => {
      // Wait for loading to finish
      const grid = page.locator('.grid')
      const noTools = page.getByText(/no tools match/i)

      // Wait for either the grid or empty message
      await expect(grid.or(noTools)).toBeVisible({ timeout: 10000 })

      // If tools are present, verify install buttons
      const installButtons = page.getByRole('button', { name: /install/i })
      const toolCount = await installButtons.count()

      if (toolCount > 0) {
        await expect(installButtons.first()).toBeVisible()
        await expect(installButtons.first()).toBeEnabled()
      }
    })

    test('refresh button is visible', async ({ page }) => {
      await expect(
        page.getByRole('button', { name: /refresh library/i }),
      ).toBeVisible()
    })
  })
})
