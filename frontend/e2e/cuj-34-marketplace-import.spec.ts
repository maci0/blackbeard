import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-34: Marketplace Import', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/marketplace')
  })

  test('marketplace page renders with heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /marketplace/i })).toBeVisible()
  })

  test('marketplace shows template gallery section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /template gallery/i })).toBeVisible()
  })

  test('template cards render with correct structure', async ({ page }) => {
    // Featured repos are hardcoded, so cards should always render
    const importButtons = page.getByRole('button', { name: /import/i })

    // Wait for cards to render
    await page.waitForTimeout(500)

    // Should have at least one import button (from the template cards)
    const count = await importButtons.count()
    expect(count).toBeGreaterThan(0)
  })

  test('template cards show preview buttons', async ({ page }) => {
    const previewButtons = page.getByRole('button', { name: /preview/i })

    await page.waitForTimeout(500)

    const count = await previewButtons.count()
    expect(count).toBeGreaterThan(0)
  })

  test('search input filters templates', async ({ page }) => {
    const searchInput = page.getByLabel(/search templates/i)
    await expect(searchInput).toBeVisible()

    // Type a search query that matches a known template
    await searchInput.fill('research')

    // Wait for filtering
    await page.waitForTimeout(300)

    // The "Research Crew Starter" should still be visible
    await expect(page.getByText(/research crew starter/i)).toBeVisible()
  })

  test('search input filters out non-matching templates', async ({ page }) => {
    const searchInput = page.getByLabel(/search templates/i)
    await searchInput.fill('xyznonexistenttemplate')

    await page.waitForTimeout(300)

    // Should show "No templates match" message
    await expect(page.getByText(/no templates match/i)).toBeVisible()
  })

  test('category filter chips are visible', async ({ page }) => {
    const categoryGroup = page.getByRole('group', {
      name: /category filters/i,
    })
    await expect(categoryGroup).toBeVisible()

    // Check for "All" category button
    const allButton = categoryGroup.getByRole('button', { name: /^all$/i })
    await expect(allButton).toBeVisible()

    // "All" should be pressed by default
    await expect(allButton).toHaveAttribute('aria-pressed', 'true')
  })

  test('clicking a category chip filters templates', async ({ page }) => {
    const categoryGroup = page.getByRole('group', {
      name: /category filters/i,
    })

    // Click on "Starter" category
    const starterButton = categoryGroup.getByRole('button', {
      name: /starter/i,
    })
    await starterButton.click()

    await expect(starterButton).toHaveAttribute('aria-pressed', 'true')

    // Should show the Research Crew Starter (which has category "Starter")
    await expect(page.getByText(/research crew starter/i)).toBeVisible()
  })

  test('clicking preview opens preview dialog', async ({ page }) => {
    const firstPreviewButton = page.getByRole('button', { name: /preview/i }).first()
    await firstPreviewButton.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Dialog should show template details
    await expect(dialog.getByText(/use case/i)).toBeVisible()
    await expect(dialog.getByText(/resources included/i)).toBeVisible()
  })

  test('preview dialog can be closed', async ({ page }) => {
    const firstPreviewButton = page.getByRole('button', { name: /preview/i }).first()
    await firstPreviewButton.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Close the dialog
    const closeButton = dialog.getByRole('button', { name: /close/i }).first()
    await closeButton.click()

    await expect(dialog).not.toBeVisible()
  })

  test('import from URL section is visible', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /import from url/i })).toBeVisible()

    const urlInput = page.getByLabel(/git repository/i)
    await expect(urlInput).toBeVisible()
  })
})
