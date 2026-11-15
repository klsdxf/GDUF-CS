import {test,expect} from '@playwright/test'
test('public navigation private fields and administrator login',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/');await expect(page.getByRole('heading',{name:'广金主场。 为这一局集结。'})).toBeVisible()
 await page.getByRole('link',{name:'战队档案',exact:true}).click();await expect(page.getByText('战队0',{exact:true})).toBeVisible()
 await page.getByText('战队0',{exact:true}).click();await expect(page.getByText('选手0-0',{exact:false})).toBeVisible()
 await expect(page.locator('body')).not.toContainText('private-contact')
 await page.goto('/admin/login');await page.getByLabel('账号',{exact:true}).fill('test-admin');await page.getByLabel('密码',{exact:true}).fill(process.env.E2E_PASSWORD||'acceptance-only-12!')
 await page.getByRole('button',{name:'登录',exact:true}).click();await expect(page.getByText('当前赛事',{exact:true})).toBeVisible()
 await page.getByRole('button',{name:'参赛名单',exact:true}).click();await expect(page.getByText('联系方式（私密）')).toBeVisible()
 expect(errors).toEqual([])
})
for(const width of [1024,761,760,541,540,390,320])for(const colorScheme of ['light','dark'] as const){
 test(`reference layout ${width} ${colorScheme}`,async({page})=>{
  await page.setViewportSize({width,height:1200});await page.emulateMedia({colorScheme})
  await page.goto('/__design-reference');await expect(page.locator('.g-mast')).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.getByRole('button',{name:'11.09'}).click();await expect(page.locator('.g-schedule-rows')).toContainText('北门突击队')
  await page.getByRole('button',{name:'赛果',exact:true}).click();await expect(page.locator('.g-schedule-rows')).toContainText('13 : 8')
  await page.screenshot({path:`test-results/reference-${width}-${colorScheme}.png`,fullPage:true})
 })
}
