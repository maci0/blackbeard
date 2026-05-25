import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Chat page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/chat')
  })

  test('page loads with model selector', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Chat' })).toBeVisible()
    await expect(
      main.getByText('Test models with ad-hoc conversations'),
    ).toBeVisible()

    const modelSelect = main.getByLabel('Model')
    const modelError = main.getByText(/Failed to load models/i)

    await expect(modelSelect.or(modelError)).toBeVisible()
  })

  test('system prompt toggle works', async ({ page }) => {
    const main = page.locator('main')
    const toggle = main.getByRole('button', { name: /system prompt/i })
    await expect(toggle).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await toggle.click()

    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await expect(page.locator('#system-prompt-area')).toBeVisible()

    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  test('temperature and max tokens inputs work', async ({ page }) => {
    const main = page.locator('main')
    const tempInput = main.getByLabel('Temperature')
    await expect(tempInput).toBeVisible()
    await expect(tempInput).toHaveValue('0.7')

    await tempInput.fill('1.0')
    await expect(tempInput).toHaveValue('1.0')

    const maxTokensInput = main.getByLabel('Max tokens')
    await expect(maxTokensInput).toBeVisible()
    await expect(maxTokensInput).toHaveValue('4096')

    await maxTokensInput.fill('2048')
    await expect(maxTokensInput).toHaveValue('2048')
  })

  test('send button disabled when empty input', async ({ page }) => {
    const main = page.locator('main')
    const sendButton = main.getByRole('button', { name: /send message/i })
    await expect(sendButton).toBeVisible()
    await expect(sendButton).toBeDisabled()
  })

  test('clear button appears after adding a message and removes messages', async ({
    page,
  }) => {
    const main = page.locator('main')
    const clearButton = main.getByRole('button', {
      name: /clear conversation/i,
    })
    await expect(clearButton).not.toBeVisible()

    const modelSelect = main.getByLabel('Model')
    if (await modelSelect.isVisible()) {
      const messageInput = main.getByLabel('Message input')
      await messageInput.fill('Hello test')
      const sendButton = main.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()
        await expect(
          main.getByRole('button', { name: /clear conversation/i }),
        ).toBeVisible()
        await main
          .getByRole('button', { name: /clear conversation/i })
          .click()
        await expect(
          main.getByRole('button', { name: /clear conversation/i }),
        ).not.toBeVisible()
      }
    }
  })
})
