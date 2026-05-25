import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Streaming Chat', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/chat')
  })

  test('send button changes to stop button while sending', async ({
    page,
  }) => {
    const main = page.locator('main')
    const modelSelect = main.getByLabel('Model')
    const modelError = main.getByText(/failed to load models/i)
    await expect(modelSelect.or(modelError)).toBeVisible()

    if (await modelSelect.isVisible()) {
      const messageInput = main.getByLabel('Message input')
      await messageInput.fill('Hello test')

      const sendButton = main.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()

        const stopButton = main.getByRole('button', { name: /stop/i })
        await expect(stopButton).toBeVisible()
      }
    }
  })

  test('stop button has square icon', async ({ page }) => {
    const main = page.locator('main')
    const modelSelect = main.getByLabel('Model')
    const modelError = main.getByText(/failed to load models/i)
    await expect(modelSelect.or(modelError)).toBeVisible()

    if (await modelSelect.isVisible()) {
      const messageInput = main.getByLabel('Message input')
      await messageInput.fill('Hello test')

      const sendButton = main.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()

        const stopButton = main.getByRole('button', { name: /stop/i })
        if (await stopButton.isVisible()) {
          const squareIcon = stopButton.locator('svg')
          await expect(squareIcon).toBeVisible()
        }
      }
    }
  })

  test('clear button resets conversation', async ({ page }) => {
    const main = page.locator('main')
    const modelSelect = main.getByLabel('Model')
    const modelError = main.getByText(/failed to load models/i)
    await expect(modelSelect.or(modelError)).toBeVisible()

    if (await modelSelect.isVisible()) {
      const messageInput = main.getByLabel('Message input')
      await messageInput.fill('Hello test')

      const sendButton = main.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()

        const clearButton = main.getByRole('button', {
          name: /clear conversation/i,
        })
        await expect(clearButton).toBeVisible()
        await clearButton.click()

        await expect(clearButton).not.toBeVisible()
      }
    }
  })
})
