import {test,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
// Production omits the preview bar by user request; compare unchanged sections.
// Apply alternate CSS theme only inside the test; there is no public theme control.
const source='http://127.0.0.1:4175/index.html'
const widths=[1920,1600,1599,1051,1050,761,760,390,381,380,320]
async function compare(actual:any,expected:any,name:string,selector='main'){
 // Apply the explicitly approved bar removal only to the test runtime.
 await expected.locator('.preview-bar').evaluateAll((els:any[])=>els.forEach(el=>el.remove()))
 await actual.locator(selector).waitFor();await expected.locator(selector).waitFor()
 for(const page of [actual,expected])await page.evaluate(async()=>{await Promise.all([500,600,700,800,900].map(w=>document.fonts.load(w+' 30px \"Barlow Condensed\"')));await document.fonts.ready})
 await actual.addStyleTag({content:'*,*:before,*:after{transition:none!important}'});await expected.addStyleTag({content:'*,*:before,*:after{transition:none!important}'})
 await actual.waitForTimeout(250);await expected.waitForTimeout(250)
 const a=`test-results/actual-${name}.png`,b=`test-results/baseline-${name}.png`
 await actual.locator(selector).screenshot({path:a,animations:'disabled'});await expected.locator(selector).screenshot({path:b,animations:'disabled'})
 const python=process.platform==='win32'?'../.venv/Scripts/python.exe':'python'
 const diff=JSON.parse(execFileSync(python,['../scripts/compare_images.py',a,b],{encoding:'utf8'}));console.log(name,JSON.stringify(diff));expect(diff.max_channel_delta).toBeLessThanOrEqual(4);expect(diff.pixels_over_one).toBeLessThanOrEqual(diff.width*diff.height*0.001)
}
for(const width of widths)for(const theme of ['blue','yellow'])test(`approved home ${width} ${theme}`,async({browser})=>{
 const context=await browser.newContext({viewport:{width,height:1000},deviceScaleFactor:1});const actual=await context.newPage(),expected=await context.newPage()
 await actual.goto('/');await expected.goto(source);await actual.locator('.public-site').evaluate((el:any,value:string)=>{el.dataset.theme=value},theme);await expected.selectOption('#accent',theme)
 await compare(actual,expected,`home-${width}-${theme}`);expect(await actual.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await context.close()
})
for(const width of [1440,390])for(const theme of ['blue','yellow'])for(const [path,hash] of [['/competitions','events'],['/competitions/autumn','event'],['/competitions/autumn/schedule','event/schedule'],['/competitions/autumn/standings','event/standings'],['/competitions/autumn/teams','event/teams'],['/competitions/autumn/rules','event/rules'],['/announcements','news'],['/matches/featured','match'],['/matches/upcoming','match/upcoming']])test(`approved ${hash} ${width} ${theme}`,async({browser})=>{
 const context=await browser.newContext({viewport:{width,height:1000},deviceScaleFactor:1});const actual=await context.newPage(),expected=await context.newPage();await actual.goto(path);await expected.goto(source+'#'+hash);await actual.locator('.public-site').evaluate((el:any,value:string)=>{el.dataset.theme=value},theme);await expected.selectOption('#accent',theme);await compare(actual,expected,hash.replaceAll('/','-')+'-'+width+'-'+theme);await context.close()
})

for(const width of [1440,390])test(`approved dialogs and map selection ${width}`,async({browser})=>{
 const context=await browser.newContext({viewport:{width,height:1000},deviceScaleFactor:1}),actual=await context.newPage(),expected=await context.newPage();
 await actual.goto('/');await expected.goto(source);await compare(actual,expected,'header-'+width,'.header');
 await actual.locator('.news-row').first().click();await expected.locator('.news-row').first().click();await compare(actual,expected,'news-dialog-'+width,'dialog');await actual.locator('#close-dialog').click();await expected.locator('#close-dialog').click();
 await actual.goto('/competitions/autumn/teams');await expected.goto(source+'#event/teams');await actual.locator('[data-team="0"]').click();await expected.locator('[data-team="0"]').click();await compare(actual,expected,'team-dialog-'+width,'dialog');await actual.locator('#close-dialog').click();await expected.locator('#close-dialog').click();
 await actual.goto('/matches/featured');await expected.goto(source+'#match');await actual.locator('[data-map="1"]').click();await expected.locator('[data-map="1"]').click();await compare(actual,expected,'map-selected-'+width);
 // The additional management link is the documented footer extension.
 await actual.locator('.footer a[href="/admin/login"]').evaluate((a:any)=>a.remove());await compare(actual,expected,'footer-'+width,'.footer');await context.close();
})
