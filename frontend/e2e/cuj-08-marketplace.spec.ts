import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-08: Marketplace Import', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/marketplace')
  })

  test('page renders with heading and description', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /marketplace/i })).toBeVisible()
    await expect(
      page.getByText(/browse and import agents, crews, and tools/i),
    ).toBeVisible()
  })

  test('template gallery section is visible with cards', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /template gallery/i })).toBeVisible()

    // At least one template card should render
    await expect(page.getByText('Research Crew Starter')).toBeVisible()
    await expect(page.getByText('Content Pipeline')).toBeVisible()
    await expect(page.getByText('Customer Support Triage')).toBeVisible()
  })

  test('import from URL section has input and submit button', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /import from url/i })).toBeVisible()

    const urlInput = page.getByPlaceholder('https://github.com/org/repo.git')
    await expect(urlInput).toBeVisible()

    // Import button should be disabled when input is empty
    const importButton = page
      .locator('form')
      .getByRole('button', { name: /^import$/i })
    await expect(importButton).toBeVisible()
    await expect(importButton).toBeDisabled()
  })

  test('search filters template cards', async ({ page }) => {
    const searchInput = page.getByPlaceholder('Search templates...')
    await expect(searchInput).toBeVisible()

    await searchInput.fill('research')
    await expect(page.getByText('Research Crew Starter')).toBeVisible()
    // Other cards should be filtered out
    await expect(page.getByText('Customer Support Triage')).not.toBeVisible()

    // Clearing search shows all cards again
    await searchInput.clear()
    await expect(page.getByText('Customer Support Triage')).toBeVisible()
  })

  test('category filter chips are visible and functional', async ({ page }) => {
    const filterGroup = page.getByRole('group', { name: /category filters/i })
    await expect(filterGroup).toBeVisible()

    // Verify category buttons exist
    await expect(filterGroup.getByRole('button', { name: 'All' })).toBeVisible()
    await expect(filterGroup.getByRole('button', { name: 'Starter' })).toBeVisible()
    await expect(filterGroup.getByRole('button', { name: 'DevTools' })).toBeVisible()

    // Click a category to filter
    await filterGroup.getByRole('button', { name: 'DevTools' }).click()
    await expect(page.getByText('Code Review Pipeline')).toBeVisible()
    await expect(page.getByText('Research Crew Starter')).not.toBeVisible()

    // Click "All" to reset
    await filterGroup.getByRole('button', { name: 'All' }).click()
    await expect(page.getByText('Research Crew Starter')).toBeVisible()
  })

  test('preview dialog opens on card preview button click', async ({ page }) => {
    const previewButton = page.getByRole('button', {
      name: /preview research crew starter/i,
    })
    await expect(previewButton).toBeVisible()
    await previewButton.click()

    // Dialog should open with template details
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Research Crew Starter')).toBeVisible()
    await expect(dialog.getByText(/use case/i)).toBeVisible()
    await expect(dialog.getByText(/resources included/i)).toBeVisible()

    // Close dialog
    await dialog.getByRole('button', { name: /close/i }).first().click()
    await expect(dialog).not.toBeVisible()
  })

  test('search with no results shows empty state', async ({ page }) => {
    const searchInput = page.getByPlaceholder('Search templates...')
    await searchInput.fill('xyznonexistenttemplate')

    await expect(page.getByText(/no templates match your search/i)).toBeVisible()
  })
})
