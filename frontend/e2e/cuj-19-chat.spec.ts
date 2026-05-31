import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-19: Chat Playground', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/chat')
  })

  test('page renders with Chat heading', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Chat' }),
    ).toBeVisible()
    await expect(
      main.getByText('Test models with ad-hoc conversations'),
    ).toBeVisible()
  })

  test('model selector or load error is visible', async ({ page }) => {
    const main = page.locator('main')
    const modelSelect = main.getByLabel('Model')
    const modelError = main.getByText(/failed to load models/i)

    await expect(modelSelect.or(modelError)).toBeVisible()
  })

  test('message input area is visible', async ({ page }) => {
    const main = page.locator('main')
    const messageInput = main.getByLabel('Message input')
    await expect(messageInput).toBeVisible()
  })

  test('send button is visible and disabled when input is empty', async ({
    page,
  }) => {
    const main = page.locator('main')
    const sendButton = main.getByRole('button', { name: /send message/i })
    await expect(sendButton).toBeVisible()
    await expect(sendButton).toBeDisabled()
  })

  test('typing a message populates the input field', async ({ page }) => {
    const main = page.locator('main')
    const messageInput = main.getByLabel('Message input')
    await messageInput.fill('Hello from the E2E test')
    await expect(messageInput).toHaveValue('Hello from the E2E test')
  })

  test('temperature input is present with default value', async ({
    page,
  }) => {
    const main = page.locator('main')
    const tempInput = main.getByLabel('Temperature')
    await expect(tempInput).toBeVisible()
    await expect(tempInput).toHaveValue('0.7')
  })

  test('max tokens input is present with default value', async ({ page }) => {
    const main = page.locator('main')
    const maxTokensInput = main.getByLabel('Max tokens')
    await expect(maxTokensInput).toBeVisible()
    await expect(maxTokensInput).toHaveValue('4096')
  })

  test('temperature input can be changed', async ({ page }) => {
    const main = page.locator('main')
    const tempInput = main.getByLabel('Temperature')
    await tempInput.fill('0.3')
    await expect(tempInput).toHaveValue('0.3')
  })

  test('system prompt toggle expands and collapses', async ({ page }) => {
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
})
