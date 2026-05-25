import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Studio', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('empty canvas shows placeholder message', async ({ page }) => {
    await expect(page.getByText('Canvas is empty')).toBeVisible()
    await expect(
      page.getByText(/drag agents and tasks from the palette/i),
    ).toBeVisible()
  })

  test('load example crew populates canvas with nodes', async ({ page }) => {
    await page.getByRole('button', { name: /load example crew/i }).click()

    // Verify the status message confirms load
    await expect(page.getByText('Example crew loaded')).toBeVisible()

    // The "Canvas is empty" message should no longer be visible
    await expect(page.getByText('Canvas is empty')).not.toBeVisible()

    // Crew name input should reflect the example crew name
    await expect(page.locator('#crew-name-input')).toHaveValue('research-crew')
  })

  test('palette has Agent, Task, and Tool items', async ({ page }) => {
    const palette = page.getByLabel('Node palette')
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

  test('toolbar shows save and run buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: /save/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /run/i })).toBeVisible()
  })

  test('toolbar shows undo and redo buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: /undo/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /redo/i })).toBeVisible()
  })
})
