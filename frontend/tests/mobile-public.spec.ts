import { expect, test, type Page } from '@playwright/test'

const api = 'http://127.0.0.1:5176'
async function resultsFixture(page: Page) {
  await page.goto('/competitions')
  return page.evaluate(async () => (await import('/src/results/demo-data.ts')).demoData())
}

for (const width of [320, 375, 390, 430]) {
  test('mobile homepage keeps its main actions and compact archive at ' + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 667 })
    await page.goto('/')
    await expect(page.locator('.gduf-home-intro')).toHaveCount(0, { timeout: 8000 })
    const photo = await page.locator('.hero-photo').boundingBox()
    const action = await page.locator('.hero-actions').boundingBox()
    expect(photo!.width).toBe(width)
    expect(photo!.height).toBeLessThan(260)
    expect(action!.y + action!.height).toBeLessThanOrEqual(667)
    const archive = await page.locator('.event-card--past').first().boundingBox()
    const current = await page.locator('.event-card--current').first().boundingBox()
    expect(archive!.height).toBeLessThan(current!.height / 2)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
  })
}

test('public mobile schedule shows the first result, filters and round destinations', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 })
  const competition = { id: 'cup', slug: 'cup', name: '校园赛', season: '2026', status: 'ongoing', competition_format: 'single' }
  const stage = { id: 'stage', name: '淘汰赛' }
  const first = {
    id: 'first', code: 'Q1', label: '半决赛', bracket: 'upper', round: 1, stage_id: stage.id,
    status: 'completed', teams: [{ name: '校园长队名 Esports' }, { name: '另一支队伍' }],
    best_of: 3, scheduled_at: '2026-11-14T11:00:00Z', confirmed: true, result: { wins_a: 2, wins_b: 1 },
  }
  const second = { ...first, id: 'final', code: 'F1', label: '决赛', round: 2, scheduled_at: '2026-11-15T11:00:00Z' }
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/competitions') ? [competition] : path.endsWith('/cup') ? competition
      : path.endsWith('/stages') ? [stage] : path.endsWith('/matches') ? [first, second]
      : path.endsWith('/bracket') ? { matches: [first, second], edges: [{ source: first.id, target: second.id, outcome: 'winner', slot: 'a' }] } : []
    return route.fulfill({ json: { data } })
  })
  await page.goto(api + '/competitions/cup/schedule')
  const fixture = page.locator('.fixture').first()
  await expect(fixture.locator('.fixture-duel')).toContainText('2 : 1')
  await expect(fixture.locator('.fixture-time')).toContainText('19:00')
  const box = await fixture.boundingBox()
  expect(box!.y + box!.height).toBeLessThanOrEqual(667)
  await page.getByRole('button', { name: '2026-11-15' }).click()
  await expect(page.locator('.fixture')).toHaveCount(1)
  await page.getByRole('button', { name: '晋级对阵' }).click()
  const picker = page.getByRole('combobox', { name: '轮次' })
  await expect(page.locator('.bracket-node:visible')).toHaveCount(1)
  await expect(page.locator('.bracket-node:visible')).toContainText('胜者 → 决赛 · F1')
  await picker.selectOption('决赛')
  await expect(page.locator('.bracket-node:visible')).toHaveAttribute('href', '/matches/final')
})

test('narrow rankings keep long rewards and providers in the row and search still filters', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 667 })
  const data = await resultsFixture(page)
  data.placements[0]!.team.name = '一支名称非常长的校园战队 CS2 Guangdong University'
  data.prizes[0]!.name = '一款名称非常长的赛事奖品 AAAAA-BBBBB-CCCCCCCC-DDDDD'
  await page.route('**/api/v1/**', route => route.fulfill({
    json: { data: new URL(route.request().url()).pathname.endsWith('/results/latest') ? data : [] },
  }))
  await page.goto(api + '/results')
  const row = page.locator('.results-table tbody tr').first()
  await expect(row).toContainText(data.placements[0]!.team.name)
  await expect(row).toContainText(data.prizes[0]!.name)
  await expect(row.getByText('奖品提供方')).toBeVisible()
  expect(await page.locator('.rank-scroll').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320)
  await page.getByRole('searchbox', { name: '搜索队伍' }).fill('不存在的战队')
  await expect(page.locator('.results-table tbody tr:visible')).toHaveCount(0)
  await expect(page.locator('#empty')).toBeVisible()
})

test('mobile pending results keep a compact seal and expose advertised rewards', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const demo = await resultsFixture(page)
  const pending = { pending: true, competition: demo.competition, display: demo.display,
    prizes: demo.prizes, partners: [demo.presenting_partner], award_plan: null }
  await page.route('**/api/v1/**', route => route.fulfill({
    json: { data: new URL(route.request().url()).pathname.endsWith('/results/latest') ? pending : [] },
  }))
  await page.goto(api + '/results')
  await expect(page.locator('.results-pending .v5-seal-scene')).toBeVisible()
  await expect(page.locator('.v4-road')).toBeHidden()
  await expect(page.getByRole('heading', { name: '最终名次与奖励' })).toBeInViewport()
})
