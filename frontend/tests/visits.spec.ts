import { expect, test } from '@playwright/test'

const publicApi = 'http://127.0.0.1:5176'

test('visible public navigation reports once and shares a browser ID across tabs', async ({ context }) => {
  const events: { visitor_id: string; kind: string }[] = []
  await context.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/visits') events.push(route.request().postDataJSON())
    const data = path === '/api/v1/competitions' ? [] : null
    return route.fulfill({ json: { data } })
  })
  await context.addInitScript(() => {
    let hidden = false
    Object.defineProperty(document, 'hidden', { get: () => hidden })
    document.addEventListener('test-hide-page', () => {
      hidden = true
      document.dispatchEvent(new Event('visibilitychange'))
    })
    document.addEventListener('test-show-page', () => {
      hidden = false
      document.dispatchEvent(new Event('visibilitychange'))
    })
  })
  const first = await context.newPage()
  const second = await context.newPage()
  await first.clock.install()
  await Promise.all([first.goto(publicApi), second.goto(publicApi + '/results')])
  await expect.poll(() => events.length).toBe(2)
  expect(events.every(event => event.kind === 'page_view')).toBe(true)
  expect(new Set(events.map(event => event.visitor_id)).size).toBe(1)
  await second.close()

  await first.evaluate(() => document.dispatchEvent(new Event('test-hide-page')))
  await first.clock.fastForward(60_000)
  expect(events).toHaveLength(2)
  await first.evaluate(() => document.dispatchEvent(new Event('test-show-page')))
  await expect.poll(() => events[2]?.kind).toBe('heartbeat')
  await first.clock.fastForward(31_000)
  await expect.poll(() => events[3]?.kind).toBe('heartbeat')

  await first.goto(publicApi + '/missing')
  await expect(first.locator('main h1')).toHaveText('页面不存在')
  await first.clock.fastForward(31_000)
  expect(events.map(event => event.kind)).toEqual(['page_view', 'page_view', 'heartbeat', 'heartbeat'])
})

test('demo pages never report visits', async ({ page }) => {
  let collected = false
  await page.route('**/api/v1/visits', route => {
    collected = true
    return route.fulfill({ json: { data: null } })
  })
  await page.clock.install()
  await page.goto('/')
  await expect(page.locator('.hero')).toBeVisible()
  await page.clock.fastForward(60_000)
  expect(collected).toBe(false)
})

test('admin displays zero, changes window, and marks the last successful snapshot on failure', async ({ page }) => {
  const ranges: string[] = []
  let failed = false
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/admin/auth/me')) {
      return route.fulfill({ json: { data: { username: 'test', csrf: 'test' } } })
    }
    if (url.pathname.endsWith('/admin/competitions')) return route.fulfill({ json: { data: [] } })
    if (!url.pathname.endsWith('/admin/visits/summary')) return route.fulfill({ json: { data: [] } })
    ranges.push(url.searchParams.get('days')!)
    if (failed) return route.fulfill({ status: 503, json: { error: { message: '服务暂不可用' } } })
    const today = { date: '2026-11-18', uv: 3, pv: 7 }
    return route.fulfill({ json: { data: {
      online: 0, as_of: '2026-11-18T10:00:00Z', tracking_started_on: '2026-11-18',
      today, daily: [{ date: '2026-11-17', uv: null, pv: null }, today], total_pv: 7,
    } } })
  })
  await page.clock.install()
  await page.goto(publicApi + '/admin/visits')
  await expect(page.getByRole('heading', { name: '访问统计' })).toBeVisible()
  await expect(page.getByTestId('visit-online')).toHaveText('0')
  await expect(page.getByTestId('visit-uv')).toHaveText('3')
  await expect(page.getByTestId('visit-total-pv')).toHaveText('7')
  await expect(page.getByText('未开始采集')).toHaveCount(2)

  await page.getByRole('button', { name: '近 30 天' }).click()
  await expect.poll(() => ranges.at(-1)).toBe('30')
  await expect(page.getByTestId('visit-pv')).toHaveText('7')
  failed = true
  await page.clock.fastForward(10_100)
  await expect(page.getByText('统计暂不可用 · 下方为上次成功数据')).toBeVisible()
  await expect(page.getByTestId('visit-online')).toHaveText('0')
})
