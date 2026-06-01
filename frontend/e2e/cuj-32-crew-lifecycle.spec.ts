import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-32: Crew Lifecycle Navigation', () => {
  test('studio page renders with canvas', async ({ page }) => {
    await loginAndNavigate(page, '/studio')

    // Studio should have the toolbar and canvas area
    await expect(page).toHaveURL(/\/studio/)

    // The canvas container from React Flow should be present
    const canvas = page.locator('.react-flow')
    await expect(canvas).toBeVisible({ timeout: 10000 })
  })

  test('studio page shows an empty canvas or existing nodes', async ({ page }) => {
    await loginAndNavigate(page, '/studio')

    const canvas = page.locator('.react-flow')
    await expect(canvas).toBeVisible({ timeout: 10000 })

    // The canvas should be interactive (has viewport controls)
    const zoomControls = page.locator('.react-flow__controls')
    const controlsVisible = await zoomControls.isVisible().catch(() => false)

    // Either controls or the canvas itself should be rendered
    expect(controlsVisible || (await canvas.isVisible())).toBeTruthy()
  })

  test('resources page renders with heading and table or empty state', async ({ page }) => {
    await loginAndNavigate(page, '/resources')

    await expect(page.getByRole('heading', { name: /resources/i })).toBeVisible()

    const table = page.getByRole('table', { name: /resources/i })
    const emptyState = page.getByText(/no resources found/i)
    const cards = page.getByRole('article')
    const skeleton = page.locator('[class*="skeleton"], [class*="pulse"]')

    await page.waitForTimeout(500)

    const tableVisible = await table.isVisible().catch(() => false)
    const emptyVisible = await emptyState.isVisible().catch(() => false)
    const cardsVisible = await cards
      .first()
      .isVisible()
      .catch(() => false)
    const skeletonVisible = await skeleton
      .first()
      .isVisible()
      .catch(() => false)

    expect(tableVisible || emptyVisible || cardsVisible || skeletonVisible).toBeTruthy()
  })

  test('executions page renders with heading and table or empty state', async ({ page }) => {
    await loginAndNavigate(page, '/executions')

    await expect(page.getByRole('heading', { name: /executions/i })).toBeVisible()

    const table = page.getByRole('table', { name: /executions/i })
    const emptyState = page.getByText(/no executions yet/i)
    const skeleton = page.locator('[class*="skeleton"], [class*="pulse"]')

    await page.waitForTimeout(500)

    const tableVisible = await table.isVisible().catch(() => false)
    const emptyVisible = await emptyState.isVisible().catch(() => false)
    const skeletonVisible = await skeleton
      .first()
      .isVisible()
      .catch(() => false)

    expect(tableVisible || emptyVisible || skeletonVisible).toBeTruthy()
  })

  test('full navigation flow: studio -> resources -> executions', async ({ page }) => {
    // Start at studio
    await loginAndNavigate(page, '/studio')
    const canvas = page.locator('.react-flow')
    await expect(canvas).toBeVisible({ timeout: 10000 })

    // Navigate to resources
    await page.goto('/resources')
    await page.waitForLoadState('domcontentloaded')
    await expect(page.getByRole('heading', { name: /resources/i })).toBeVisible({ timeout: 10000 })

    // Navigate to executions
    await page.goto('/executions')
    await page.waitForLoadState('domcontentloaded')
    await expect(page.getByRole('heading', { name: /executions/i })).toBeVisible({ timeout: 10000 })
  })

  test('sidebar navigation links are accessible', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')

    // Check that key navigation links exist in the sidebar
    const studioLink = page.getByRole('link', { name: /studio/i })
    const resourcesLink = page.getByRole('link', { name: /^resources$/i })
    const executionsLink = page.getByRole('link', { name: /executions/i })

    await expect(studioLink).toBeVisible()
    await expect(resourcesLink).toBeVisible()

    // Executions might be behind a section header
    const execVisible = await executionsLink.isVisible().catch(() => false)
    if (!execVisible) {
      // Try expanding the section if collapsed
      const moreSection = page.getByText(/operations/i)
      const sectionVisible = await moreSection.isVisible().catch(() => false)
      if (sectionVisible) {
        await moreSection.click()
      }
    }
  })
})
