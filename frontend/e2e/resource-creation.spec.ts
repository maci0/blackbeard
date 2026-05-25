import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Resource Creation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/resources')
  })

  test('resources page has New Resource button', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByRole('button', { name: /new resource/i }),
    ).toBeVisible()
  })

  test('Paste YAML button opens dialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /paste yaml/i }).click()

    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(
      page.getByRole('textbox', { name: /yaml/i }).or(
        page.locator('textarea'),
      ),
    ).toBeVisible()
  })

  test('New Resource dialog has kind dropdown with all 13 kinds', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /new resource/i }).click()

    await expect(page.getByRole('dialog')).toBeVisible()

    const dialog = page.getByRole('dialog')
    const kindSelect = dialog.getByLabel(/kind/i).or(
      dialog.getByRole('combobox', { name: /kind/i }),
    )
    await expect(kindSelect).toBeVisible()

    const kinds = [
      'Agent',
      'Task',
      'Crew',
      'Tool',
      'LLMConnection',
      'AgentPolicy',
      'Guardrail',
      'Flow',
      'KnowledgeSource',
      'Role',
      'RoleBinding',
      'Automation',
      'Namespace',
    ]

    await kindSelect.click()

    for (const kind of kinds) {
      await expect(
        page.getByRole('option', { name: new RegExp(`^${kind}$`, 'i') }).or(
          page.getByText(new RegExp(`^${kind}$`)),
        ),
      ).toBeVisible()
    }
  })

  test('resource creation dialog has name and spec fields', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /new resource/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByLabel(/name/i).or(
        dialog.getByRole('textbox', { name: /name/i }),
      ),
    ).toBeVisible()
    await expect(
      dialog.getByLabel(/spec/i).or(dialog.getByText(/spec/i)),
    ).toBeVisible()
  })
})
