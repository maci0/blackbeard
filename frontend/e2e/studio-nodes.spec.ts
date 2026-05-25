import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Studio Nodes', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('palette shows all 9 node types', async ({ page }) => {
    const main = page.locator('main')
    const palette = main.getByLabel('Node palette')
    await expect(palette).toBeVisible()

    const nodeTypes = [
      'Agent',
      'Task',
      'Tool',
      'Flow Step',
      'PII Filter',
      'Condition',
      'Router',
      'Parallel',
      'Note',
    ]

    for (const nodeType of nodeTypes) {
      await expect(
        palette.getByRole('button', {
          name: new RegExp(`add ${nodeType} node`, 'i'),
        }),
      ).toBeVisible()
    }
  })

  test('sticky note has editable text area', async ({ page }) => {
    const main = page.locator('main')
    const palette = main.getByLabel('Node palette')
    await palette
      .getByRole('button', { name: /add note node/i })
      .click()

    const noteTextarea = main
      .getByRole('textbox', { name: /note/i })
      .or(main.locator('.react-flow__node-note textarea'))
    await expect(noteTextarea).toBeVisible()
  })

  test('property panel shows for selected node', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /load example crew/i }).click()
    await expect(main.getByText('Example crew loaded')).toBeVisible()

    const node = main.locator('.react-flow__node').first()
    await node.click()

    await expect(
      main.locator('h1, h2, h3').filter({ hasText: /properties/i }).or(
        main.getByLabel(/property panel/i),
      ),
    ).toBeVisible()
  })

  test('expression editor appears for condition nodes', async ({ page }) => {
    const main = page.locator('main')
    const palette = main.getByLabel('Node palette')
    await palette
      .getByRole('button', { name: /add condition node/i })
      .click()

    const conditionNode = main.locator('.react-flow__node-condition').or(
      main.locator('[data-testid="condition-node"]'),
    )
    await conditionNode.click()

    await expect(
      main.getByLabel(/expression/i).or(main.getByText(/expression editor/i)),
    ).toBeVisible()
  })

  test('crew settings button in toolbar', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByRole('button', { name: /crew settings/i }),
    ).toBeVisible()
  })

  test('export dropdown in toolbar with export options', async ({ page }) => {
    const main = page.locator('main')
    const exportBtn = main.getByRole('button', { name: /export/i })
    await expect(exportBtn).toBeVisible()
    await exportBtn.click()

    await expect(page.getByRole('menuitem', { name: /export json/i }).or(
      page.getByText(/export json/i),
    )).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /copy as json/i }).or(
      page.getByText(/copy as json/i),
    )).toBeVisible()
  })
})
