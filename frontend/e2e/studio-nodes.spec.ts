import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Studio Nodes', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('palette shows all 9 node types', async ({ page }) => {
    const palette = page.getByLabel('Node palette')
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
    const palette = page.getByLabel('Node palette')
    await palette
      .getByRole('button', { name: /add note node/i })
      .click()

    const noteTextarea = page
      .getByRole('textbox', { name: /note/i })
      .or(page.locator('.react-flow__node-note textarea'))
    await expect(noteTextarea).toBeVisible()
  })

  test('property panel shows for selected node', async ({ page }) => {
    await page.getByRole('button', { name: /load example crew/i }).click()
    await expect(page.getByText('Example crew loaded')).toBeVisible()

    const node = page.locator('.react-flow__node').first()
    await node.click()

    await expect(
      page.getByRole('heading', { name: /properties/i }).or(
        page.getByLabel(/property panel/i),
      ),
    ).toBeVisible()
  })

  test('expression editor appears for condition nodes', async ({ page }) => {
    const palette = page.getByLabel('Node palette')
    await palette
      .getByRole('button', { name: /add condition node/i })
      .click()

    const conditionNode = page.locator('.react-flow__node-condition').or(
      page.locator('[data-testid="condition-node"]'),
    )
    await conditionNode.click()

    await expect(
      page.getByLabel(/expression/i).or(page.getByText(/expression editor/i)),
    ).toBeVisible()
  })

  test('crew settings button in toolbar', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /crew settings/i }),
    ).toBeVisible()
  })

  test('export dropdown in toolbar with export options', async ({ page }) => {
    const exportBtn = page.getByRole('button', { name: /export/i })
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
