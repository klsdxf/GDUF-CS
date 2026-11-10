import {test,expect} from '@playwright/test'
import {pathToFileURL} from 'node:url'
import {mkdirSync} from 'node:fs'
import {expectSealMotion} from './seal-motion'
test.use({video:'on'})
for(const url of ['/results','/results/autumn'])test(`seal responds on first entry and after remount: ${url}`,async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.addInitScript(()=>{
  const bindings=new Set<EventTarget>();(window as any).__sealBindings=bindings
  const add=EventTarget.prototype.addEventListener,remove=EventTarget.prototype.removeEventListener
  EventTarget.prototype.addEventListener=function(type,...args){if(type==='pointermove'&&this instanceof Element&&this.matches('.v4-champion'))bindings.add(this);return add.call(this,type,...args)}
  EventTarget.prototype.removeEventListener=function(type,...args){if(type==='pointermove')bindings.delete(this);return remove.call(this,type,...args)}
 })
 await page.setViewportSize({width:1280,height:900})
 await page.goto(url)
 await expectSealMotion(page)
 for(const award of [1,2,0]){
  await page.locator(`[data-award="${award}"]`).click()
  await expectSealMotion(page)
  expect(await page.evaluate(()=>(window as any).__sealBindings.size)).toBe(1)
 }
 await page.locator('.main-nav a').filter({hasText:'首页'}).click()
 await expect(page.locator('.v5-seal-object')).toHaveCount(0)
 expect(await page.evaluate(()=>(window as any).__sealBindings.size)).toBe(0)
 await page.locator('.main-nav a').filter({hasText:'最终排名'}).click()
 await expectSealMotion(page)
 await page.reload()
 await expectSealMotion(page)
 expect(errors).toEqual([])
})

test('seal does not apply desktop tilt to a touch pointer',async({browser})=>{
 const context=await browser.newContext({hasTouch:true,isMobile:true,viewport:{width:390,height:844}})
 const page=await context.newPage()
 await page.goto('/results');await expect(page.locator('.v5-seal-object')).toBeVisible()
 expect(await page.evaluate(()=>matchMedia('(hover:hover) and (pointer:fine)').matches)).toBeFalsy()
 await page.locator('.v5-seal-scene').dispatchEvent('pointermove',{clientX:100,clientY:100})
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))
 expect(await page.locator('.v5-seal-object').evaluate(el=>el.style.getPropertyValue('--seal-rx'))).toBe('')
 await page.locator('[data-award="1"]').click();await expect(page.locator('#product-title')).toHaveText('K75 机械键盘')
 await context.close()
})

test('results navigation, search, awards, dialogs, motion and offline export',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/results');await expect(page.locator('.main-nav a.active')).toHaveText('最终排名')
 await expect(page.locator('.v4-type h3')).toContainText('木棉 FIVE');await expect(page.locator('.results-table tbody tr')).toHaveCount(8)
 await page.locator('#search').fill('FINANCE');await expect(page.locator('[data-team]:visible')).toHaveCount(1);await page.locator('#search').fill('不存在');await expect(page.locator('#empty')).toBeVisible();await page.locator('#search').fill('')
 await page.locator('[data-award="1"]').click();await expect(page.locator('#product-title')).toHaveText('K75 机械键盘');await page.keyboard.press('End');await expect(page.locator('#product-title')).toHaveText('M4 无线鼠标');await page.locator('#product-detail').click();await expect(page.locator('#result-dialog')).toContainText('北苑竞技');await page.keyboard.press('Escape');await expect(page.locator('#product-detail')).toBeFocused()
 await page.locator('.v4-win-bottom button').click();await expect(page.locator('#result-dialog .map-detail')).toHaveCount(4);await page.keyboard.press('Escape')
 await expect(page.locator('.public-site')).toHaveClass(/v5-motion-on/)
 await expect(page.locator('.v5-seal-reflection')).toHaveCSS('animation-duration','9s')
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'下载此预览'}).click();const file=await download;const offlinePath=test.info().outputPath('results-offline.html');await file.saveAs(offlinePath)
 for(const w of [1920,1600,1599,1280,1051,1050,768,761,760,390,381,380,360,320]){await page.setViewportSize({width:w,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),String(w)).toBeTruthy()}
 const before=await page.locator('.v5-seal-object').evaluate(el=>getComputedStyle(el).transform);await page.setViewportSize({width:1280,height:900});await page.locator('.v5-seal-scene').hover({position:{x:50,y:50}});await expect.poll(()=>page.locator('.v5-seal-object').evaluate(el=>getComputedStyle(el).transform)).not.toBe(before)
 const offline=await page.context().newPage();await offline.route('http**/*',r=>r.abort());await offline.goto(pathToFileURL(offlinePath).href);await expect(offline.locator('.results-table tbody tr')).toHaveCount(8);await offline.locator('[data-award="1"]').click();await expect(offline.locator('#product-title')).toHaveText('K75 机械键盘');await offline.locator('#product-detail').click();await expect(offline.locator('dialog')).toContainText('金融风暴');await offline.close()
 expect(errors).toEqual([])
 mkdirSync('../reports/results-v6',{recursive:true});await page.close();await page.video()?.saveAs('../reports/results-v6/interactions.webm')
})
test('API result empty/error states never show a demo champion',async({page})=>{
 await page.route('**/api/v1/**',r=>r.fulfill({json:{data:null}}));await page.goto('http://127.0.0.1:5176/results');await expect(page.locator('main')).toContainText('最终排名待公布');await expect(page.locator('main')).not.toContainText('木棉')
 await page.route('**/api/v1/**',r=>r.fulfill({status:503,json:{error:{message:'结果服务暂不可用'}}}));await page.reload();await expect(page.locator('main')).toContainText('结果服务暂不可用')
 await page.route('**/api/v1/**',r=>r.fulfill({status:404,json:{error:{message:'不存在'}}}));await page.goto('http://127.0.0.1:5176/results/unknown');await expect(page.locator('main')).toContainText('页面不存在')
})
