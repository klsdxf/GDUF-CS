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

for (const width of [320, 375, 390, 430]) {
  test('schedule cards and connected bracket columns fit at ' + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 667 })
    const competition = { id: 'cup', slug: 'cup', name: '校园赛', season: '2026', status: 'ongoing', competition_format: 'single' }
    const stage = { id: 'stage', name: '淘汰赛', type: 'single' }
    const otherStage = { id: 'other', name: '附加赛', type: 'single' }
    const first = {
      id: 'first', code: 'Q1', label: '半决赛', bracket: 'upper', round: 1, stage_id: stage.id,
      status: 'completed', teams: [{ name: '校园战队 AAAAAAAAABBBBBBBBBCCCCCCCCCDDDDDDDDD' }, { name: '另一支名字非常长的中文队伍' }],
      best_of: 3, scheduled_at: '2026-11-14T11:00:00Z', confirmed: true, result: { wins_a: 2, wins_b: 1 },
    }
    const second = { ...first, id: 'second', code: 'Q2' }
    const final = { ...first, id: 'final', code: 'F1', label: '决赛', round: 2, scheduled_at: '2026-11-15T11:00:00Z',
      teams: [null, null], confirmed: false, source_a: 'Q1:winner', source_b: 'Q2:winner' }
    const bronze = { ...final, id: 'bronze', code: 'T1', label: '季军赛', bracket: 'third' }
    const extra = { ...final, id: 'extra', code: 'E1', stage_id: otherStage.id }
    await page.route('**/api/v1/**', route => {
      const path = new URL(route.request().url()).pathname
      const data = path.endsWith('/competitions') ? [competition] : path.endsWith('/cup') ? competition
        : path.endsWith('/stages') ? [stage, otherStage] : path.endsWith('/matches') ? [first, second, final, extra]
        : path.endsWith('/stage/bracket') ? {
          matches: [first, second, bronze, final],
          edges: [
            { source: first.id, target: bronze.id, outcome: 'loser', slot: 'a' },
            { source: second.id, target: bronze.id, outcome: 'loser', slot: 'b' },
            { source: first.id, target: final.id, outcome: 'winner', slot: 'a' },
            { source: second.id, target: final.id, outcome: 'winner', slot: 'b' },
          ],
        }
        : path.endsWith('/other/bracket') ? { matches: [extra] } : []
      return route.fulfill({ json: { data } })
    })
    const schedule = api + '/competitions/cup/schedule'
    const fixtures = page.locator('.fixture')
    const firstFixture = fixtures.first()
    const fitsViewport = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
    await page.goto(schedule)
    const rows = firstFixture.locator('.fixture-team')
    const scores = firstFixture.locator('.fixture-team-score')
    await expect(scores).toHaveText(['2', '1'])
    await expect(firstFixture.locator('.fixture-series-score')).toBeHidden()
    await expect(rows.first()).toContainText(first.teams[0]!.name)
    await expect(firstFixture.locator('.fixture-time')).toContainText('19:00')
    await expect(fixtures.nth(2).locator('.fixture-team-score')).toHaveText(['–', '–'])
    const topRow = await rows.first().boundingBox(), bottomRow = await rows.last().boundingBox()
    const homeScore = await scores.first().boundingBox(), awayScore = await scores.last().boundingBox()
    expect(bottomRow!.y).toBeGreaterThanOrEqual(topRow!.y + topRow!.height)
    expect(homeScore!.x + homeScore!.width).toBeCloseTo(awayScore!.x + awayScore!.width)
    const box = await firstFixture.boundingBox(), following = await fixtures.nth(1).boundingBox()
    expect(following!.y - box!.y - box!.height).toBeGreaterThanOrEqual(12)
    expect(await fitsViewport()).toBe(true)
    if (width === 375) expect(box!.y + box!.height).toBeLessThanOrEqual(667)

    await page.getByRole('button', { name: '2026-11-15' }).click()
    await expect(fixtures).toHaveCount(2)
    await page.locator('select[data-stage]').selectOption(stage.id)
    await expect(fixtures).toHaveCount(1)
    await expect(fixtures.first()).toHaveAttribute('href', '/matches/final')
    await page.getByRole('button', { name: '晋级对阵' }).click()
    const controls = page.locator('.bracket-filters')
    await expect(controls.locator('select[data-stage]')).toHaveValue(stage.id)
    const board = page.getByRole('region', { name: /晋级对阵/ })
    const lanes = board.locator('.bracket-round')
    await expect(lanes.locator('h2')).toHaveText(['半决赛', '季军赛', '决赛'])
    await expect(board.locator('.bracket-node')).toHaveCount(4)
    const firstLane = await lanes.first().boundingBox(), secondLane = await lanes.nth(1).boundingBox()
    const viewport = await board.boundingBox()
    expect(firstLane!.y).toBeCloseTo(secondLane!.y)
    expect(secondLane!.x).toBeGreaterThan(firstLane!.x + firstLane!.width)
    expect(secondLane!.x + secondLane!.width).toBeLessThanOrEqual(viewport!.x + viewport!.width + 1)
    const cards = lanes.first().locator('.bracket-node')
    const firstCard = await cards.first().boundingBox(), secondCard = await cards.last().boundingBox()
    expect(secondCard!.y - firstCard!.y - firstCard!.height).toBeGreaterThanOrEqual(12)
    await expect(board.locator('.bracket-connections path')).toHaveCount(4)
    await expect(board.locator('.bracket-loser-edge')).toHaveCount(2)
    const finalCard = board.locator('a[href="/matches/final"]')
    const finalPath = await board.locator('.bracket-connections path:not(.bracket-loser-edge)').first().getAttribute('d')
    await board.evaluate(element => { element.scrollLeft = element.scrollWidth })
    await expect(finalCard).toBeInViewport()
    await expect(board.locator('.bracket-connections path:not(.bracket-loser-edge)').first()).toHaveAttribute('d', finalPath!)
    await controls.locator('select[data-stage]').selectOption(otherStage.id)
    await expect(board.locator('.bracket-node')).toHaveAttribute('href', '/matches/extra')
    await expect(board.getByRole('heading', { name: '决赛', exact: true })).toBeVisible()
    expect(await fitsViewport()).toBe(true)

    if (width === 430) {
      await page.setViewportSize({ width: 1440, height: 900 })
      await page.goto(schedule)
      await expect(firstFixture.locator('.fixture-series-score')).toBeVisible()
      await expect(firstFixture.locator('.fixture-team-score').first()).toBeHidden()

      await page.goto(schedule + '?view=bracket&stage=' + stage.id)
      await expect(lanes.locator('h2')).toHaveText(['半决赛', '季军赛', '决赛'])
      await expect(board.locator('.bracket-connections path')).toHaveCount(4)
      await expect(board.locator('.bracket-loser-edge')).toHaveCount(2)
      await expect(page.getByText('实线胜者 · 虚线败者')).toBeVisible()
      await expect(finalCard).toBeInViewport()
      expect(await board.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
      const desktopHeaders = await lanes.locator('h2').evaluateAll(headings => headings.map(heading => heading.getBoundingClientRect().top))
      expect(new Set(desktopHeaders).size).toBe(1)
    }
  })
}

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
