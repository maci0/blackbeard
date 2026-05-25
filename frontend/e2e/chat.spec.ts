import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Chat page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/chat')
  })

  test('page loads with model selector', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible()
    await expect(
      page.getByText('Test models with ad-hoc conversations'),
    ).toBeVisible()

    const modelSelect = page.getByLabel('Model')
    const modelError = page.getByText(/Failed to load models/i)

    await expect(modelSelect.or(modelError)).toBeVisible()
  })

  test('system prompt toggle works', async ({ page }) => {
    const toggle = page.getByRole('button', { name: /system prompt/i })
    await expect(toggle).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await toggle.click()

    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await expect(page.locator('#system-prompt-area')).toBeVisible()

    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  test('temperature and max tokens inputs work', async ({ page }) => {
    const tempInput = page.getByLabel('Temperature')
    await expect(tempInput).toBeVisible()
    await expect(tempInput).toHaveValue('0.7')

    await tempInput.fill('1.0')
    await expect(tempInput).toHaveValue('1.0')

    const maxTokensInput = page.getByLabel('Max tokens')
    await expect(maxTokensInput).toBeVisible()
    await expect(maxTokensInput).toHaveValue('4096')

    await maxTokensInput.fill('2048')
    await expect(maxTokensInput).toHaveValue('2048')
  })

  test('send button disabled when empty input', async ({ page }) => {
    const sendButton = page.getByRole('button', { name: /send message/i })
    await expect(sendButton).toBeVisible()
    await expect(sendButton).toBeDisabled()
  })

  test('clear button appears after adding a message and removes messages', async ({
    page,
  }) => {
    const clearButton = page.getByRole('button', {
      name: /clear conversation/i,
    })
    await expect(clearButton).not.toBeVisible()

    const modelSelect = page.getByLabel('Model')
    if (await modelSelect.isVisible()) {
      const messageInput = page.getByLabel('Message input')
      await messageInput.fill('Hello test')
      const sendButton = page.getByRole('button', { name: /send message/i })
      if (await sendButton.isEnabled()) {
        await sendButton.click()
        await expect(
          page.getByRole('button', { name: /clear conversation/i }),
        ).toBeVisible()
        await page
          .getByRole('button', { name: /clear conversation/i })
          .click()
        await expect(
          page.getByRole('button', { name: /clear conversation/i }),
        ).not.toBeVisible()
      }
    }
  })
})
