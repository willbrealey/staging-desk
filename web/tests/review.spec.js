import { expect, test } from '@playwright/test'

const caseButton = (page, id) => page.locator('button[data-case="' + id + '"]')

test('product owner compares both translations and records a reversible local decision', async ({ page }) => {
  await page.goto('./')
  await expect(caseButton(page, 'ready')).toHaveAttribute('aria-current', 'true')
  await expect(page.locator('.proposed p')).toHaveAttribute('lang', 'en')
  await page.getByRole('button', { name: 'Deutsch' }).click()
  await expect(page.locator('.proposed p')).toHaveAttribute('lang', 'de')
  await expect(page.locator('.proposed p')).toContainText('3')
  await page.getByRole('button', { name: 'Run evidence' }).click()
  await expect(page.getByRole('heading', { name: 'Independent checks' })).toBeVisible()
  await expect(page.locator('.provenance code')).toHaveText(/^[0-9a-f]{64}$/)
  await page.getByRole('button', { name: 'Approve for staging' }).click()
  await page.reload()
  await expect(page.getByText('Approved for staging', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Reset decision' }).click()
  await page.getByRole('button', { name: 'Request changes' }).click()
  await expect(page.getByText('Changes requested', { exact: true })).toBeVisible()
})

test('a blocked translation exposes the failing check and cannot be approved', async ({ page }) => {
  await page.goto('./#blocked')
  await expect(caseButton(page, 'blocked')).toHaveAttribute('aria-current', 'true')
  await page.getByRole('button', { name: 'Deutsch' }).click()
  await expect(page.locator('.proposed p')).not.toContainText('3')
  await page.getByRole('button', { name: 'Run evidence' }).click()
  await expect(page.locator('.checks li').filter({ hasText: 'Failed' })).toContainText(/count/i)
  await expect(page.getByRole('button', { name: 'Approve for staging' })).toHaveCount(0)
})

test('an out-of-scope request has an engineer handoff and no publication action', async ({ page }) => {
  await page.goto('./')
  await caseButton(page, 'escalated').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Routed to engineering' })).toBeVisible()
  await page.getByRole('button', { name: 'Engineering handoff' }).click()
  await expect(page.getByRole('textbox')).toHaveValue(/Routing reason:/)
  await expect(page.getByRole('button', { name: 'Approve for staging' })).toHaveCount(0)
})

test('an old decision does not approve a different recorded review', async ({ page }) => {
  await page.goto('./#ready')
  await page.getByRole('button', { name: 'Approve for staging' }).click()
  await page.route('**/cases.json', async route => {
    const response = await route.fetch()
    const rows = await response.json()
    rows.find(row => row.id === 'ready').sha256 = '0'.repeat(64)
    await route.fulfill({ json: rows })
  })
  await page.reload()
  await expect(page.getByRole('button', { name: 'Approve for staging' })).toBeVisible()
})

test('phone layout exposes each workflow without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('./')
  for (const id of ['ready', 'blocked', 'escalated']) {
    await caseButton(page, id).click()
    await expect(caseButton(page, id)).toHaveAttribute('aria-current', 'true')
    await page.getByRole('button', { name: 'Run evidence' }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
})

test('keyboard skip link focuses the same case without rewriting its route', async ({ page }) => {
  for (const id of ['blocked', 'escalated']) {
    await page.goto('./#' + id)
    const selectedCase = caseButton(page, id)
    await expect(selectedCase).toHaveAttribute('aria-current', 'true')
    await page.getByRole('link', { name: 'Skip to selected request' }).focus()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(new RegExp('#' + id + '$'))
    await expect(selectedCase).toHaveAttribute('aria-current', 'true')
    await expect(page.locator('article#review')).toBeFocused()
  }
})
