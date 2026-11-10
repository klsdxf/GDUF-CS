import {test,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import {existsSync,writeFileSync,mkdirSync} from 'node:fs'
for(const width of [1920,1600,1599,1280,1051,1050,768,761,760,390,381,380,360,320])test(`V6 frozen comparison ${width}`,async({browser})=>{
 const ctx=await browser.newContext({viewport:{width,height:900},deviceScaleFactor:1}),actual=await ctx.newPage(),frozen=await ctx.newPage()
 await actual.goto('/results');await frozen.goto('http://127.0.0.1:4175/results-v6')
 // Vue loads the results chunk asynchronously; wait for its DOM/CSS before fonts.ready.
 for(const page of [actual,frozen])await expect(page.locator('.v5-seal-object')).toBeVisible()
 for(const page of [actual,frozen]){await page.evaluate(()=>document.fonts.ready);await page.addStyleTag({content:'*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}.v5-enter,.v5-enter-late,.v5-seal-arrive,.v5-reveal{opacity:1!important;transform:none!important}'})}
 const selectors=['.header','.v5-toolbar','.v4-champion','.v4-runners','.v4-road','.v4-standings','.v4-equipment','.v4-sponsors','.v5-seal-object']
 for(const s of selectors){const a=await actual.locator(s).boundingBox(),b=await frozen.locator(s).boundingBox();expect(a,`${width} ${s}`).not.toBeNull();for(const k of ['x','y','width','height'] as const)expect(Math.abs(a![k]-b![k]),`${s} ${k}`).toBeLessThanOrEqual(1)}
 mkdirSync('../reports/results-v6',{recursive:true})
 const a=`test-results/results-${width}.png`,b=`test-results/frozen-results-${width}.png`
 await actual.locator('main').screenshot({path:a});await frozen.locator('main').screenshot({path:b})
 const diff=JSON.parse(execFileSync(process.platform==='win32'&&existsSync('../.venv/Scripts/python.exe')?'../.venv/Scripts/python.exe':'python',['../scripts/compare_images.py',a,b],{encoding:'utf8'}));writeFileSync(`../reports/results-v6/diff-${width}.json`,JSON.stringify(diff));expect(diff.pixels_over_one/(diff.width*diff.height)).toBeLessThan(.001)
 if([390,1920].includes(width))await actual.locator('main').screenshot({path:`../reports/results-v6/results-${width}.png`})
 await ctx.close()
})
