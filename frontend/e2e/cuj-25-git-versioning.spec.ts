import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('CUJ-25: Git Version Control', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('GET /api/v1/git/log returns entries array', async ({ page }) => {
    const response = await page.request.get('/api/v1/git/log')

    expect(response.ok()).toBe(true)
    expect(response.status()).toBe(200)

    const body = await response.json()
    expect(body).toHaveProperty('entries')
    expect(body).toHaveProperty('total')
    expect(Array.isArray(body.entries)).toBe(true)
    expect(typeof body.total).toBe('number')
    expect(body.total).toBe(body.entries.length)
  })

  test('git log entries have expected fields', async ({ page }) => {
    const response = await page.request.get('/api/v1/git/log')
    const body = await response.json()

    for (const entry of body.entries) {
      expect(entry).toHaveProperty('commit')
      expect(entry).toHaveProperty('author')
      expect(entry).toHaveProperty('email')
      expect(entry).toHaveProperty('timestamp')
      expect(entry).toHaveProperty('message')
      expect(typeof entry.commit).toBe('string')
      expect(typeof entry.author).toBe('string')
      expect(typeof entry.message).toBe('string')
    }
  })

  test('git log accepts a limit parameter', async ({ page }) => {
    const response = await page.request.get('/api/v1/git/log?limit=5')

    expect(response.ok()).toBe(true)

    const body = await response.json()
    expect(body.entries.length).toBeLessThanOrEqual(5)
  })

  test('GET /api/v1/git/diff returns diff data', async ({ page }) => {
    const response = await page.request.get('/api/v1/git/diff')

    expect(response.ok()).toBe(true)

    const body = await response.json()
    expect(body).toHaveProperty('diff')
    expect(body).toHaveProperty('commit_a')
    expect(body).toHaveProperty('commit_b')
    expect(typeof body.diff).toBe('string')
  })
})
