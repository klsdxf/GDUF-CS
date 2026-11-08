import {test,expect} from '@playwright/test'
import {readFileSync} from 'node:fs'
import {resolve} from 'node:path'
import {execFileSync} from 'node:child_process'
test('compare Vue reference against immutable source in same browser',async({browser})=>{
 const source=readFileSync(resolve('../开发文档/前端设计基准/广金主场_观赛优先_选定稿.fragment.html'),'utf8')
 for(const width of [1024,761,760,541,540,390,320])for(const colorScheme of ['light','dark'] as const){
  const context=await browser.newContext({viewport:{width,height:1200},colorScheme})
  const actual=await context.newPage();await actual.goto('http://localhost:5173/__design-reference');await expect(actual.locator('.g-button svg')).toBeVisible()
  const icon=await actual.locator('.g-button svg').evaluate(e=>e.outerHTML)
  const expected=await context.newPage();await expected.setContent('<!doctype html><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+source.replace('<i data-lucide="arrow-down-right" aria-hidden="true"></i>',icon));await expected.evaluate(()=>document.fonts.ready)
  const a=await actual.locator('.g-site').screenshot({path:`test-results/actual-${width}-${colorScheme}.png`})
  const b=await expected.locator('.g-site').screenshot({path:`test-results/baseline-${width}-${colorScheme}.png`})
  const python=process.env.PYTHON||(process.platform==='win32'?'../.venv/Scripts/python.exe':'python')
  const diff=JSON.parse(execFileSync(python,['../scripts/compare_images.py',`test-results/actual-${width}-${colorScheme}.png`,`test-results/baseline-${width}-${colorScheme}.png`],{encoding:'utf8'}))
  console.log(`${width} ${colorScheme}: ${JSON.stringify(diff)}`)
  expect(diff.max_channel_delta,`pixel comparison ${width} ${colorScheme}; allow only 1/255 raster rounding`).toBeLessThanOrEqual(1)
  await context.close()
 }
})
