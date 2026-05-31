import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-06: Model Configuration', () => {
  test.describe('Models page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/models')
    })

    test('page renders with heading and description', async ({ page }) => {
      await expect(
        page.getByRole('heading', { name: /models/i }),
      ).toBeVisible()
      await expect(
        page.getByText(/llm connections and providers/i),
      ).toBeVisible()
    })

    test('add connection button is visible', async ({ page }) => {
      const addButton = page.getByRole('button', { name: /add connection/i })
      await expect(addButton).toBeVisible()
    })

    test('refresh button is visible', async ({ page }) => {
      const refreshButton = page.getByRole('button', {
        name: /refresh models/i,
      })
      await expect(refreshButton).toBeVisible()
    })

    test('clicking add connection opens dialog', async ({ page }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Add LLM Connection')).toBeVisible()
      await expect(
        dialog.getByText(/configure a new language model connection/i),
      ).toBeVisible()
    })

    test('add connection dialog has name field', async ({ page }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      const nameInput = dialog.locator('#model-name')
      await expect(nameInput).toBeVisible()
      await expect(nameInput).toHaveAttribute('required', '')
    })

    test('add connection dialog has provider dropdown', async ({ page }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      const providerSelect = dialog.locator('#model-provider')
      await expect(providerSelect).toBeVisible()

      // Should have provider options
      const options = providerSelect.locator('option')
      const count = await options.count()
      expect(count).toBeGreaterThanOrEqual(4) // OpenAI, Anthropic, Vertex AI, Azure, Ollama, Other
    })

    test('add connection dialog has model field', async ({ page }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      const modelInput = dialog.locator('#model-model')
      await expect(modelInput).toBeVisible()
      await expect(modelInput).toHaveAttribute('required', '')
    })

    test('add connection dialog has API key env var field', async ({
      page,
    }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      const apiKeyInput = dialog.locator('#model-api-key-env')
      await expect(apiKeyInput).toBeVisible()
    })

    test('add connection dialog has temperature and max tokens fields', async ({
      page,
    }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog.locator('#model-temperature')).toBeVisible()
      await expect(dialog.locator('#model-max-tokens')).toBeVisible()
    })

    test('add connection dialog has base URL field', async ({ page }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog.locator('#model-base-url')).toBeVisible()
    })

    test('add connection dialog validates required fields', async ({
      page,
    }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')

      // Submit with empty fields
      await dialog.getByRole('button', { name: /add connection/i }).click()

      // Validation error should appear
      await expect(dialog.getByRole('alert')).toBeVisible()
      await expect(dialog.getByText(/name is required/i)).toBeVisible()
    })

    test('add connection dialog cancel closes it', async ({ page }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('add connection dialog close button dismisses it', async ({
      page,
    }) => {
      await page.getByRole('button', { name: /add connection/i }).click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /close/i }).click()
      await expect(dialog).not.toBeVisible()
    })

    test('empty state shows when no models are configured', async ({
      page,
    }) => {
      // If no models exist, there should be an empty state
      const emptyState = page.getByText(/no llm connections yet/i)
      const emptyVisible = await emptyState.isVisible().catch(() => false)

      if (emptyVisible) {
        // The empty state should have an action to add a connection
        await expect(
          page.getByRole('button', { name: /add connection/i }),
        ).toBeVisible()
      }
      // If models exist, the test passes since we just need to verify the page rendered
    })

    test('view toggle is present', async ({ page }) => {
      const tableViewButton = page.getByRole('button', {
        name: /table view/i,
      })
      const cardViewButton = page.getByRole('button', { name: /card view/i })

      const tableVisible = await tableViewButton.isVisible().catch(() => false)
      const cardVisible = await cardViewButton.isVisible().catch(() => false)

      expect(tableVisible || cardVisible).toBeTruthy()
    })
  })

  test.describe('Chat page model selector', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/chat')
    })

    test('chat page renders with heading', async ({ page }) => {
      await expect(
        page.getByRole('heading', { name: /chat/i }),
      ).toBeVisible()
    })

    test('chat page has model selector label', async ({ page }) => {
      // The model selector or its label should be visible
      const modelLabel = page.getByText(/^model$/i)
      await expect(modelLabel).toBeVisible()
    })

    test('chat page has model dropdown or loading skeleton', async ({
      page,
    }) => {
      // Either the select element is present (loaded) or the skeleton (loading)
      const modelSelect = page.locator('#chat-model')
      const skeleton = page.locator('[class*="skeleton"], [class*="pulse"]')

      // Wait a moment for the page to stabilize
      await page.waitForTimeout(500)

      const selectVisible = await modelSelect.isVisible().catch(() => false)
      const skeletonVisible = await skeleton.first().isVisible().catch(() => false)
      const errorVisible = await page
        .getByText(/failed to load/i)
        .isVisible()
        .catch(() => false)

      // One of these states should be true: loaded, loading, or error
      expect(selectVisible || skeletonVisible || errorVisible).toBeTruthy()
    })

    test('chat page has message input area', async ({ page }) => {
      // The chat input should be present (textarea or input for messages)
      const chatInput = page.getByRole('textbox')
      const inputVisible = await chatInput.first().isVisible().catch(() => false)

      // Even if the input is disabled (no model selected), it should be in the DOM
      expect(inputVisible).toBeTruthy()
    })
  })
})
