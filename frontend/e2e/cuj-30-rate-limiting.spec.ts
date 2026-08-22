import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('CUJ-30: Rate Limiting', () => {
  test('rapid API calls are handled without crashing', async ({ page }) => {
    await login(page)

    // Fire 10 rapid requests to the resources endpoint
    const results = await Promise.allSettled(
      Array.from({ length: 10 }, () =>
        page.request.get('/api/v1/agents', {
          headers: {
            Accept: 'application/json',
          },
        }),
      ),
    )

    const fulfilled = results.filter((r) => r.status === 'fulfilled')
    expect(fulfilled.length).toBeGreaterThan(0)

    // Check response statuses
    const statuses = fulfilled.map((r) => r.value.status())

    // At least some should succeed (200)
    const successCount = statuses.filter((s) => s === 200).length
    expect(successCount).toBeGreaterThan(0)

    // If rate limiting is active, some may return 429
    const rateLimitedCount = statuses.filter((s) => s === 429).length

    if (rateLimitedCount > 0) {
      // Verify rate-limited responses have appropriate structure
      for (const result of fulfilled) {
        if (result.value.status() === 429) {
          const body = await result.value.text()
          // Should contain error information
          expect(body.length).toBeGreaterThan(0)
        }
      }
    }
  })

  test('API calls return proper JSON structure', async ({ page }) => {
    await login(page)

    const response = await page.request.get('/api/v1/agents', {
      headers: {
        Accept: 'application/json',
      },
    })

    expect(response.status()).toBe(200)

    const body = await response.json()
    expect(body).toHaveProperty('items')
    expect(body).toHaveProperty('total')
  })

  test('sequential rapid calls maintain data consistency', async ({ page }) => {
    await login(page)

    // Make calls sequentially and verify consistent responses
    const responses: number[] = []
    for (let i = 0; i < 5; i++) {
      const response = await page.request.get('/api/v1/agents', {
        headers: {
          Accept: 'application/json',
        },
      })
      responses.push(response.status())
    }

    // All sequential calls should succeed or be rate-limited, not error
    for (const status of responses) {
      expect([200, 429]).toContain(status)
    }
  })
})
