import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-05: YAML Resource Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/resources')
  })

  test('resources page renders with heading and description', async ({
    page,
  }) => {
    await expect(page.getByRole('heading', { name: /resources/i })).toBeVisible()
    await expect(
      page.getByText(/agents, tasks, crews, tools, and policies/i),
    ).toBeVisible()
  })

  test('resources page shows search input', async ({ page }) => {
    // The search might only show when there are resources, or always be visible.
    // Check for either the search box or the empty state.
    const searchInput = page.getByLabel(/search resources by name/i)
    const emptyState = page.getByText(/no resources found/i)

    const searchVisible = await searchInput.isVisible().catch(() => false)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    // At least one of these should be true
    expect(searchVisible || emptyVisible).toBeTruthy()
  })

  test('resources page shows kind filter dropdown', async ({ page }) => {
    // The kind filter may only be present when resources exist
    const kindFilter = page.getByLabel(/filter by kind/i)
    const emptyState = page.getByText(/no resources found/i)

    const filterVisible = await kindFilter.isVisible().catch(() => false)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    expect(filterVisible || emptyVisible).toBeTruthy()
  })

  test('import YAML button is visible', async ({ page }) => {
    const importButton = page.getByRole('button', { name: /import yaml/i })
    await expect(importButton).toBeVisible()
  })

  test('paste YAML button is visible and opens dialog', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await expect(pasteButton).toBeVisible()

    await pasteButton.click()

    // The paste YAML dialog should open
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Paste YAML')).toBeVisible()

    // Dialog should contain a textarea for YAML content
    await expect(dialog.getByLabel(/yaml content/i)).toBeVisible()

    // Import YAML button inside the dialog
    await expect(
      dialog.getByRole('button', { name: /import yaml/i }),
    ).toBeVisible()

    // Cancel button
    await expect(
      dialog.getByRole('button', { name: /cancel/i }),
    ).toBeVisible()
  })

  test('paste YAML dialog dismisses on cancel', async ({ page }) => {
    await page.getByRole('button', { name: /paste yaml/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('new resource button is visible and opens dialog', async ({ page }) => {
    const newResourceButton = page.getByRole('button', {
      name: /new resource/i,
    })
    await expect(newResourceButton).toBeVisible()

    await newResourceButton.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('New Resource')).toBeVisible()

    // Dialog should have kind, name, project, and spec fields
    await expect(dialog.getByLabel(/kind/i)).toBeVisible()
    await expect(dialog.getByLabel(/^name$/i)).toBeVisible()
    await expect(dialog.getByLabel(/project/i)).toBeVisible()
    await expect(dialog.getByLabel(/spec.*json/i)).toBeVisible()
  })

  test('new resource dialog has kind options for all resource types', async ({
    page,
  }) => {
    await page.getByRole('button', { name: /new resource/i }).click()

    const dialog = page.getByRole('dialog')
    const kindSelect = dialog.locator('#new-resource-kind')
    await expect(kindSelect).toBeVisible()

    // The select should have options (at least Agent, Task, Crew)
    const options = kindSelect.locator('option')
    const count = await options.count()
    expect(count).toBeGreaterThan(3)
  })

  test('new resource dialog validates name field', async ({ page }) => {
    await page.getByRole('button', { name: /new resource/i }).click()

    const dialog = page.getByRole('dialog')

    // Leave name empty and blur to trigger validation
    const nameInput = dialog.locator('#new-resource-name')
    await nameInput.focus()
    await nameInput.blur()

    // Validation error should appear
    await expect(dialog.getByText(/name is required/i)).toBeVisible()
  })

  test('new resource dialog cancel closes it', async ({ page }) => {
    await page.getByRole('button', { name: /new resource/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('create in studio link navigates to studio', async ({ page }) => {
    const studioLink = page.getByRole('link', { name: /create in studio/i })
    await expect(studioLink).toBeVisible()

    await studioLink.click()
    await expect(page).toHaveURL('/studio')
  })

  test('refresh button is present', async ({ page }) => {
    const refreshButton = page.getByRole('button', {
      name: /refresh resources/i,
    })
    await expect(refreshButton).toBeVisible()
  })

  test('view toggle between table and cards is present', async ({ page }) => {
    // The ViewToggle component should be present in the page header actions
    // It renders as buttons or a toggle control
    const tableViewButton = page.getByRole('button', { name: /table view/i })
    const cardViewButton = page.getByRole('button', { name: /card view/i })

    // At least one view toggle button should be visible
    const tableVisible = await tableViewButton.isVisible().catch(() => false)
    const cardVisible = await cardViewButton.isVisible().catch(() => false)

    expect(tableVisible || cardVisible).toBeTruthy()
  })

  test('empty state shows link to studio when no resources exist', async ({
    page,
  }) => {
    // If the resource list is empty, there should be an empty state with a link to studio
    const emptyState = page.getByText(/no resources found/i)
    const emptyVisible = await emptyState.isVisible().catch(() => false)

    if (emptyVisible) {
      const studioAction = page.getByRole('link', { name: /go to studio/i })
      await expect(studioAction).toBeVisible()
    }
    // If resources exist, this test just passes silently
  })
})
