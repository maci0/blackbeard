import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-15: Project Management', () => {
  test.describe('Projects page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/projects')
    })

    test('page renders with heading and description', async ({ page }) => {
      await expect(
        page.getByRole('heading', { name: /projects/i }),
      ).toBeVisible()
      await expect(
        page.getByText(/manage project scopes, quotas, and guardrails/i),
      ).toBeVisible()
    })

    test('new project button is visible', async ({ page }) => {
      await expect(
        page.getByRole('button', { name: /new project/i }),
      ).toBeVisible()
    })

    test('refresh button is visible', async ({ page }) => {
      await expect(
        page.getByRole('button', { name: /refresh/i }),
      ).toBeVisible()
    })

    test('clicking new project opens creation dialog', async ({ page }) => {
      await page.getByRole('button', { name: /new project/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(
        dialog.getByRole('heading', { name: /new project/i }),
      ).toBeVisible()

      // Name field
      const nameInput = dialog.getByLabel(/^name/i)
      await expect(nameInput).toBeVisible()
      await expect(nameInput).toHaveAttribute('placeholder', 'my-project')

      // Description field
      const descInput = dialog.getByLabel(/description/i)
      await expect(descInput).toBeVisible()
    })

    test('dialog describes the purpose of projects', async ({ page }) => {
      await page.getByRole('button', { name: /new project/i }).click()
      const dialog = page.getByRole('dialog')

      await expect(
        dialog.getByText(/projects group resources and apply shared guardrails/i),
      ).toBeVisible()
    })

    test('create and cancel buttons are in the dialog', async ({ page }) => {
      await page.getByRole('button', { name: /new project/i }).click()
      const dialog = page.getByRole('dialog')

      await expect(
        dialog.getByRole('button', { name: /^create$/i }),
      ).toBeVisible()
      await expect(
        dialog.getByRole('button', { name: /cancel/i }),
      ).toBeVisible()
    })

    test('cancel button closes creation dialog', async ({ page }) => {
      await page.getByRole('button', { name: /new project/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('close button (X) closes creation dialog', async ({ page }) => {
      await page.getByRole('button', { name: /new project/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /close/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('shows empty state or project table', async ({ page }) => {
      const emptyState = page.getByText(/no projects yet/i)
      const table = page.getByRole('table')

      await expect(emptyState.or(table)).toBeVisible()
    })

    test('project table has expected columns when projects exist', async ({
      page,
    }) => {
      const table = page.getByRole('table')

      if (await table.isVisible()) {
        await expect(table.getByText('Name')).toBeVisible()
        await expect(table.getByText('Description')).toBeVisible()
        await expect(table.getByText('Guardrails')).toBeVisible()
        await expect(table.getByText('Quota')).toBeVisible()
      }
    })

    test('default project has a badge and no delete button', async ({
      page,
    }) => {
      const table = page.getByRole('table')

      if (await table.isVisible()) {
        const defaultRow = table.locator('tr', { hasText: 'default' })
        if ((await defaultRow.count()) > 0) {
          // "default" badge should be visible
          await expect(defaultRow.getByText('default').first()).toBeVisible()

          // Delete button should not be present for the default project
          await expect(
            defaultRow.getByRole('button', { name: /delete/i }),
          ).not.toBeVisible()
        }
      }
    })

    test('filter input works when projects exist', async ({ page }) => {
      const table = page.getByRole('table')

      if (await table.isVisible()) {
        const filterInput = page.getByRole('textbox', {
          name: /filter projects/i,
        })
        await expect(filterInput).toBeVisible()

        await filterInput.fill('nonexistentproject')
        await expect(
          page.getByText(/no projects match/i),
        ).toBeVisible()

        await filterInput.clear()
        await expect(table).toBeVisible()
      }
    })
  })

  test.describe('Project switcher in sidebar', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/dashboard')
    })

    test('project switcher shows default project', async ({ page }) => {
      await expect(
        page
          .getByRole('button', { name: /default/i })
          .or(page.getByText(/project.*default/i)),
      ).toBeVisible()
    })

    test('clicking project switcher opens dropdown', async ({ page }) => {
      const switcher = page
        .getByRole('button', { name: /project/i })
        .or(page.getByRole('button', { name: /default/i }))

      await switcher.click()

      // Dropdown should appear with at least "default" listed
      await expect(page.getByText('default')).toBeVisible()
    })
  })
})
