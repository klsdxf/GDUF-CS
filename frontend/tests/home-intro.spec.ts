import { expect, test } from '@playwright/test'

for (const viewport of [{width: 1440, height: 900}, {width: 390, height: 844}]) {
  test(`home opening hands the same poster to the original layout at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/')
    const opening = page.locator('.gduf-home-intro')
    const site = page.locator('.public-site')
    const poster = site.locator('.hero-photo')
    await expect(opening).toBeVisible()
    await expect(site).toHaveAttribute('inert', '')
    await expect(poster).toHaveJSProperty('complete', true)
    await expect(opening.locator('.gduf-scenery img')).toHaveJSProperty('complete', true)
    const original = await poster.boundingBox()

    await opening.evaluate(node => {
      for (const animation of node.getAnimations({ subtree: true })) {
        animation.pause()
        animation.currentTime = 2300
      }
      const clock = node.getAnimations().find(track =>
        track instanceof CSSAnimation && track.animationName === 'gduf-intro-clock')
      clock?.finish()
    })
    await expect(site).toHaveAttribute('data-home-intro-landing', '')
    const result = await opening.evaluate(node => {
      for (const track of node.getAnimations({ subtree: true })) {
        if (track instanceof CSSAnimation || track instanceof CSSTransition) continue
        track.pause()
        track.currentTime = 705
      }
      const scene = node.querySelector('.gduf-scenery')!
      const incoming = scene.querySelector('img')!
      const poster = document.querySelector<HTMLImageElement>('.public-site .hero-photo')!
      const movingBox = scene.getBoundingClientRect()
      const homeBox = poster.getBoundingClientRect()
      return {
        sameImage: incoming.currentSrc === poster.currentSrc,
        error: Math.max(...(['x', 'y', 'width', 'height'] as const)
          .map(key => Math.abs(movingBox[key] - homeBox[key]))),
        hiddenPhoto: getComputedStyle(poster).visibility,
        portraitOpacity: getComputedStyle(node.querySelector('.gduf-player')!).opacity
      }
    })
    expect(result.sameImage).toBe(true)
    expect(result.error).toBeLessThanOrEqual(1)
    expect(result.hiddenPhoto).toBe('hidden')
    expect(result.portraitOpacity).toBe('0')

    await opening.evaluate(node => {
      const scene = node.querySelector('.gduf-scenery')!
      scene.getAnimations().find(track =>
        (track.effect as KeyframeEffect | null)?.getKeyframes()[0]?.clipPath)?.finish()
    })
    await expect(opening).toHaveCount(0)
    await expect(site).not.toHaveAttribute('inert')
    expect(await poster.boundingBox()).toEqual(original)
    await expect(page.getByRole('link', {name: /进入赛事/}).first()).toBeVisible()
  })
}

test('open or reload starts once even under reduced motion; in-site navigation does not restart it', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/competitions')
  const opening = page.locator('.gduf-home-intro')
  await expect(opening).toHaveCount(0)
  await page.getByRole('navigation', {name: '主导航'}).getByRole('link', {name: '首页'}).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(opening).toHaveCount(0)

  await page.reload()
  await expect(opening).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(opening).toHaveCount(0)
  await page.reload()
  await expect(opening).toBeVisible()
  await expect(opening).toHaveCount(0, {timeout: 6000})
  await expect(page.locator('.public-site')).not.toHaveAttribute('inert')
  await expect(page.getByRole('navigation', {name: '主导航'})).toBeVisible()
})

test('a slow API releases the opening without blocking the original loading state', async ({ page }) => {
  let release!: () => void
  const ready = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/competitions', async route => {
    await ready
    await route.fulfill({json: {data: []}})
  })
  try {
    await page.goto('http://127.0.0.1:5176/')
    const opening = page.locator('.gduf-home-intro')
    await expect(opening).toBeVisible()
    await expect(opening).toHaveCount(0, {timeout: 6000})
    await expect(page.getByText('正在加载赛事信息…')).toBeVisible()
    release()
    await expect(page.locator('.hero')).toContainText('赛事尚未公布')
    await expect(opening).toHaveCount(0)
  } finally {
    release()
  }
})
