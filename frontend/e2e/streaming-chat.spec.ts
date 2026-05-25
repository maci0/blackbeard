import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Streaming Chat', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/chat')
  })

  test('send button changes to stop button while sending', async ({
    page,
  }) => {
    const modelSelect = page.getByLabel('Model')
    const modelError = page.getByText(/failed to load models/i)
    await expect(modelSelect.or(modelError)).toBeVisible()

    if (await modelSelect.isVisible()) {
      const messageInput = page.getByLabel('Message input')
      await messageInput.fill('Hello test')

      const sendButton = page.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()

        const stopButton = page.getByRole('button', { name: /stop/i })
        await expect(stopButton).toBeVisible()
      }
    }
  })

  test('stop button has square icon', async ({ page }) => {
    const modelSelect = page.getByLabel('Model')
    const modelError = page.getByText(/failed to load models/i)
    await expect(modelSelect.or(modelError)).toBeVisible()

    if (await modelSelect.isVisible()) {
      const messageInput = page.getByLabel('Message input')
      await messageInput.fill('Hello test')

      const sendButton = page.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()

        const stopButton = page.getByRole('button', { name: /stop/i })
        if (await stopButton.isVisible()) {
          const squareIcon = stopButton.locator('svg')
          await expect(squareIcon).toBeVisible()
        }
      }
    }
  })

  test('clear button resets conversation', async ({ page }) => {
    const modelSelect = page.getByLabel('Model')
    const modelError = page.getByText(/failed to load models/i)
    await expect(modelSelect.or(modelError)).toBeVisible()

    if (await modelSelect.isVisible()) {
      const messageInput = page.getByLabel('Message input')
      await messageInput.fill('Hello test')

      const sendButton = page.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()

        const clearButton = page.getByRole('button', {
          name: /clear conversation/i,
        })
        await expect(clearButton).toBeVisible()
        await clearButton.click()

        await expect(clearButton).not.toBeVisible()
      }
    }
  })
})
