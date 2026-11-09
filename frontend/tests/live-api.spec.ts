import {test,expect} from '@playwright/test'
test.skip(!process.env.E2E_PUBLIC_BASE_URL,'需要独立验收库的 API 模式页面')
test.use({baseURL:process.env.E2E_PUBLIC_BASE_URL||'http://127.0.0.1:5185'})
test('published backend data reaches new public frontend and stable deep links',async({page,request})=>{
 const list=(await (await request.get('/api/v1/competitions')).json()).data;const c=list.find((c:any)=>c.name==='浏览器验收杯');expect(c).toBeTruthy()
 await page.goto('/competitions/'+c.slug);await expect(page.locator('main')).toContainText('浏览器验收杯');await expect(page.locator('main')).not.toContainText('木棉 FIVE')
 await page.goto('/competitions/'+c.slug+'/schedule?view=bracket');await expect(page.locator('.bracket-board')).toContainText('战队0')
 const matches=(await (await request.get('/api/v1/competitions/'+c.slug+'/matches')).json()).data
 const completed=matches.find((m:any)=>m.confirmed);expect(completed).toBeTruthy();await page.goto('/matches/'+completed.id);await expect(page.locator('#map-report')).toContainText('13');await expect(page.locator('.rosters')).toContainText(completed.teams[0].members[0].nickname);await expect(page.locator('body')).not.toContainText('private-contact');await expect(page.locator('body')).not.toContainText('76561198')
 const teams=(await (await request.get('/api/v1/competitions/'+c.slug+'/teams')).json()).data;await page.goto('/competitions/'+c.slug+'/teams/'+teams[0].id);await expect(page.locator('dialog')).toContainText('正式')
})
