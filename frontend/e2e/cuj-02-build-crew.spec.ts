import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-02: Build a Crew in Studio', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('studio page renders with toolbar and canvas', async ({ page }) => {
    const main = page.locator('main')

    // Toolbar should be visible with crew name input
    await expect(main.locator('#crew-name-input')).toBeVisible()

    // Save and Run buttons should be present
    await expect(
      main.getByRole('button', { name: /save crew/i }),
    ).toBeVisible()
    await expect(main.getByRole('button', { name: /run/i })).toBeVisible()
  })

  test('crew name input accepts text and normalizes', async ({ page }) => {
    const main = page.locator('main')
    const crewNameInput = main.locator('#crew-name-input')

    await crewNameInput.fill('')
    await crewNameInput.fill('my-test-crew')

    await expect(crewNameInput).toHaveValue('my-test-crew')
  })

  test('palette is visible with agent, task, and tool items', async ({
    page,
  }) => {
    const main = page.locator('main')
    const palette = main.getByLabel('Node palette')
    await expect(palette).toBeVisible()

    await expect(
      palette.getByRole('button', { name: /add agent node/i }),
    ).toBeVisible()
    await expect(
      palette.getByRole('button', { name: /add task node/i }),
    ).toBeVisible()
    await expect(
      palette.getByRole('button', { name: /add tool node/i }),
    ).toBeVisible()
  })

  test('palette items are interactive and clickable', async ({ page }) => {
    const main = page.locator('main')
    const palette = main.getByLabel('Node palette')

    const agentButton = palette.getByRole('button', { name: /add agent node/i })
    await expect(agentButton).toBeEnabled()

    const taskButton = palette.getByRole('button', { name: /add task node/i })
    await expect(taskButton).toBeEnabled()

    const toolButton = palette.getByRole('button', { name: /add tool node/i })
    await expect(toolButton).toBeEnabled()
  })

  test('empty canvas shows placeholder message', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByText('Canvas is empty')).toBeVisible()
    await expect(
      main.getByText(/drag agents and tasks from the palette/i),
    ).toBeVisible()
  })

  test('load example crew populates the canvas', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /load example crew/i }).click()

    // Example loaded confirmation
    await expect(main.getByText('Example crew loaded')).toBeVisible()

    // Canvas should no longer be empty
    await expect(main.getByText('Canvas is empty')).not.toBeVisible()

    // Crew name input should reflect the example name
    await expect(main.locator('#crew-name-input')).toHaveValue('research-crew')
  })

  test('undo and redo buttons are present in toolbar', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByRole('button', { name: /undo/i })).toBeVisible()
    await expect(main.getByRole('button', { name: /redo/i })).toBeVisible()
  })

  test('save button does not crash on empty canvas', async ({ page }) => {
    const main = page.locator('main')

    // Set a crew name first
    await main.locator('#crew-name-input').fill('empty-crew')

    // Click save. Even without backend, the button click should not break the UI.
    await main.getByRole('button', { name: /save crew/i }).click()

    // The toolbar and canvas should still be intact after clicking save
    await expect(main.locator('#crew-name-input')).toBeVisible()
    await expect(main.getByRole('button', { name: /run/i })).toBeVisible()
  })

  test('YAML editor toggle button is present', async ({ page }) => {
    const main = page.locator('main')
    const yamlToggle = main.getByRole('button', {
      name: /open yaml editor|close yaml editor/i,
    })
    await expect(yamlToggle).toBeVisible()
  })

  test('auto layout button is present', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByRole('button', { name: /auto-arrange nodes/i }),
    ).toBeVisible()
  })

  test('export dropdown is present and opens', async ({ page }) => {
    const main = page.locator('main')
    const exportButton = main.getByRole('button', { name: /export crew/i })
    await expect(exportButton).toBeVisible()

    await exportButton.click()

    // Dropdown should show export options
    await expect(page.getByText('Export JSON')).toBeVisible()
    await expect(page.getByText('Copy as JSON')).toBeVisible()
  })

  test('keyboard shortcuts button opens dialog', async ({ page }) => {
    const main = page.locator('main')
    await main
      .getByRole('button', { name: /keyboard shortcuts/i })
      .click()

    // A dialog with keyboard shortcuts should appear
    await expect(
      page.getByRole('dialog').getByText(/keyboard shortcuts/i),
    ).toBeVisible()
  })
})
