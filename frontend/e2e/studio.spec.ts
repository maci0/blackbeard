import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Studio', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('empty canvas shows placeholder message', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByText('Canvas is empty')).toBeVisible()
    await expect(
      main.getByText(/drag agents and tasks from the palette/i),
    ).toBeVisible()
  })

  test('load example crew populates canvas with nodes', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /load example crew/i }).click()

    // Verify the status message confirms load
    await expect(main.getByText('Example crew loaded')).toBeVisible()

    // The "Canvas is empty" message should no longer be visible
    await expect(main.getByText('Canvas is empty')).not.toBeVisible()

    // Crew name input should reflect the example crew name
    await expect(main.locator('#crew-name-input')).toHaveValue('research-crew')
  })

  test('palette has Agent, Task, and Tool items', async ({ page }) => {
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

  test('toolbar shows save and run buttons', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByRole('button', { name: /save crew/i })).toBeVisible()
    await expect(main.getByRole('button', { name: /run/i })).toBeVisible()
  })

  test('toolbar shows undo and redo buttons', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByRole('button', { name: /undo/i })).toBeVisible()
    await expect(main.getByRole('button', { name: /redo/i })).toBeVisible()
  })
})
