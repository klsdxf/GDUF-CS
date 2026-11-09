import {test,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import {existsSync} from 'node:fs'
// Frozen approval remains immutable. Compare only the unchanged brand artwork.
for(const width of [360,390,768,1280])test(`frozen brand artwork ${width}`,async({browser})=>{
 const context=await browser.newContext({viewport:{width,height:844},deviceScaleFactor:1}),actual=await context.newPage(),expected=await context.newPage()
 await actual.goto('/');await expected.goto('http://127.0.0.1:4175/index.html');await expected.locator('.preview-bar').evaluate(el=>el.remove());for(const p of [actual,expected])await p.evaluate(()=>document.fonts.ready)
 const a=`test-results/brand-${width}.png`,b=`test-results/frozen-brand-${width}.png`
 await actual.locator('.brand-symbol').screenshot({path:a});await expected.locator('.brand-symbol').screenshot({path:b})
 const diff=JSON.parse(execFileSync(process.platform==='win32'&&existsSync('../.venv/Scripts/python.exe')?'../.venv/Scripts/python.exe':'python',['../scripts/compare_images.py',a,b],{encoding:'utf8'}));expect(diff.max_channel_delta).toBeLessThanOrEqual(4);expect(diff.pixels_over_one).toBeLessThanOrEqual(diff.width*diff.height*.001);await context.close()
})
const baselinePlatform=process.env.VISUAL_BASELINE_PLATFORM
if(baselinePlatform&&baselinePlatform!=='windows-server-2025')throw new Error('Unknown visual baseline platform')
// F-01/02/03/04/06/10: reviewed repair baselines, separate from frozen design.
for(const width of [360,390,768,1280])for(const [name,path] of [['home','/'],['score','/matches/featured'],['schedule','/competitions/autumn/schedule'],['standings','/competitions/autumn/standings'],['teams','/competitions/autumn/teams'],['rules','/competitions/autumn/rules'],['overview','/competitions/autumn'],['news','/announcements']])test(`audit repair ${name} ${width}`,async({page})=>{
 await page.setViewportSize({width,height:844});await page.goto(path);await page.evaluate(()=>document.fonts.ready)
 await expect(page.locator('.public-site')).toHaveScreenshot(baselinePlatform?[baselinePlatform,`audit-${name}-${width}.png`]:`audit-${name}-${width}.png`,{animations:'disabled',maxDiffPixelRatio:.001})
})
