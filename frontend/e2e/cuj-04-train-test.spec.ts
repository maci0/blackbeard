import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-04: Train and Test', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('RunDialog Train mode tab exists and is selectable', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    const modeGroup = dialog.getByRole('radiogroup', {
      name: /execution mode/i,
    })

    const trainRadio = modeGroup.getByRole('radio', { name: /train/i })
    await expect(trainRadio).toBeVisible()

    // Click to select Train mode
    await trainRadio.click()
    await expect(trainRadio).toHaveAttribute('aria-checked', 'true')

    // Dialog title should change to "Train Crew"
    await expect(dialog.getByText('Train Crew')).toBeVisible()
  })

  test('RunDialog Test mode tab exists and is selectable', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    const modeGroup = dialog.getByRole('radiogroup', {
      name: /execution mode/i,
    })

    const testRadio = modeGroup.getByRole('radio', { name: /test/i })
    await expect(testRadio).toBeVisible()

    // Click to select Test mode
    await testRadio.click()
    await expect(testRadio).toHaveAttribute('aria-checked', 'true')

    // Dialog title should change to "Test Crew"
    await expect(dialog.getByText('Test Crew')).toBeVisible()
  })

  test('switching between all three modes updates dialog header', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    const modeGroup = dialog.getByRole('radiogroup', {
      name: /execution mode/i,
    })

    // Start in Run mode
    await expect(dialog.getByText('Run Crew')).toBeVisible()

    // Switch to Train
    await modeGroup.getByRole('radio', { name: /train/i }).click()
    await expect(dialog.getByText('Train Crew')).toBeVisible()

    // Switch to Test
    await modeGroup.getByRole('radio', { name: /test/i }).click()
    await expect(dialog.getByText('Test Crew')).toBeVisible()

    // Switch back to Run
    await modeGroup.getByRole('radio', { name: /^Run$/i }).click()
    await expect(dialog.getByText('Run Crew')).toBeVisible()
  })

  test('Train mode shows iterations field', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // In Run mode, iterations field should NOT be visible
    await expect(dialog.locator('#run-dialog-iterations')).not.toBeVisible()

    // Switch to Train mode
    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /train/i })
      .click()

    // Iterations field should now be visible
    await expect(dialog.locator('#run-dialog-iterations')).toBeVisible()

    // Verify default value is 3
    await expect(dialog.locator('#run-dialog-iterations')).toHaveValue('3')
  })

  test('Test mode shows iterations field', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // Switch to Test mode
    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /test/i })
      .click()

    // Iterations field should be visible
    await expect(dialog.locator('#run-dialog-iterations')).toBeVisible()
    await expect(dialog.locator('#run-dialog-iterations')).toHaveValue('3')
  })

  test('Train mode shows output file field', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // In Run mode, output file should NOT be visible
    await expect(dialog.locator('#run-dialog-filename')).not.toBeVisible()

    // Switch to Train mode
    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /train/i })
      .click()

    // Output file field should now be visible with default value
    await expect(dialog.locator('#run-dialog-filename')).toBeVisible()
    await expect(dialog.locator('#run-dialog-filename')).toHaveValue(
      'training_data.pkl',
    )
  })

  test('Test mode does NOT show output file field', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // Switch to Test mode
    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /test/i })
      .click()

    // Iterations should be visible but output file should NOT
    await expect(dialog.locator('#run-dialog-iterations')).toBeVisible()
    await expect(dialog.locator('#run-dialog-filename')).not.toBeVisible()
  })

  test('iterations field accepts numeric input within bounds', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // Switch to Train mode
    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /train/i })
      .click()

    const iterationsInput = dialog.locator('#run-dialog-iterations')
    await expect(iterationsInput).toBeVisible()

    // Change the value
    await iterationsInput.fill('10')
    await expect(iterationsInput).toHaveValue('10')

    // Min attribute should be 1, max should be 100
    await expect(iterationsInput).toHaveAttribute('min', '1')
    await expect(iterationsInput).toHaveAttribute('max', '100')
  })

  test('Train mode shows description about training iterations', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /train/i })
      .click()

    // Description hint should reference "training iterations"
    await expect(
      dialog.getByText(/number of training iterations/i),
    ).toBeVisible()
  })

  test('Test mode shows description about test iterations', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /test/i })
      .click()

    // Description hint should reference "test iterations"
    await expect(
      dialog.getByText(/number of test iterations/i),
    ).toBeVisible()
  })

  test('Train mode submit button label changes to Train', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /train/i })
      .click()

    // The submit button text should be "Train"
    const submitButtons = dialog.getByRole('button')
    await expect(
      submitButtons.filter({ hasText: /^Train$/ }),
    ).toBeVisible()
  })

  test('Test mode submit button label changes to Test', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /test/i })
      .click()

    // The submit button text should be "Test"
    const submitButtons = dialog.getByRole('button')
    await expect(
      submitButtons.filter({ hasText: /^Test$/ }),
    ).toBeVisible()
  })
})
