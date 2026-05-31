import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-23: Observability Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/observability')
  })

  test('page renders with Observability heading', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Observability' })).toBeVisible()
  })

  test('page shows description text', async ({ page }) => {
    await expect(
      page.getByText('Budget, execution, and safety metrics across your platform'),
    ).toBeVisible()
  })

  test('Budget Utilization section is visible', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h2').filter({ hasText: 'Budget Utilization' })).toBeVisible()
  })

  test('Execution Metrics section is visible', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h2').filter({ hasText: 'Execution Metrics' })).toBeVisible()
  })

  test('Token Usage section is visible', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h2').filter({ hasText: 'Token Usage' })).toBeVisible()
  })

  test('Policy and Safety section is visible', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h2').filter({ hasText: 'Policy and Safety' })).toBeVisible()
  })

  test('Budget stat cards are displayed', async ({ page }) => {
    const main = page.locator('main')
    const budgetSection = main.locator('section[aria-labelledby="budget-section-heading"]')
    await expect(budgetSection).toBeVisible()

    await expect(budgetSection.getByText('Total Spend')).toBeVisible()
    await expect(budgetSection.getByText('Budget Remaining')).toBeVisible()
    await expect(budgetSection.getByText('Spend Rate')).toBeVisible()
  })

  test('Execution stat cards are displayed', async ({ page }) => {
    const main = page.locator('main')
    const execSection = main.locator('section[aria-labelledby="execution-section-heading"]')
    await expect(execSection).toBeVisible()

    await expect(execSection.getByText('Total Executions')).toBeVisible()
    await expect(execSection.getByText('Success Rate')).toBeVisible()
    await expect(execSection.getByText('Avg Duration')).toBeVisible()
    await expect(execSection.getByText('Active Now')).toBeVisible()
  })

  test('Token stat cards are displayed', async ({ page }) => {
    const main = page.locator('main')
    const tokenSection = main.locator('section[aria-labelledby="token-section-heading"]')
    await expect(tokenSection).toBeVisible()

    await expect(tokenSection.getByText('Total Tokens')).toBeVisible()
    await expect(tokenSection.getByText('Prompt Tokens')).toBeVisible()
    await expect(tokenSection.getByText('Completion Tokens')).toBeVisible()
  })

  test('Policy stat cards are displayed', async ({ page }) => {
    const main = page.locator('main')
    const safetySection = main.locator('section[aria-labelledby="safety-section-heading"]')
    await expect(safetySection).toBeVisible()

    await expect(safetySection.getByText('Policy Denials')).toBeVisible()
    await expect(safetySection.getByText('Guardrail Triggers')).toBeVisible()
    await expect(safetySection.getByText('Budget Exceeded')).toBeVisible()
  })

  test('refresh button is visible and clickable', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh data/i })
    await expect(refreshBtn).toBeVisible()

    // Click should not cause an error
    await refreshBtn.click()

    // Page should still show the heading after refresh
    await expect(
      page.locator('main').locator('h1').filter({ hasText: 'Observability' }),
    ).toBeVisible()
  })
})
