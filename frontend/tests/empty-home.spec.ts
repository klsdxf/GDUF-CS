import {test,expect} from '@playwright/test'

test('new production database retains homepage design without invented results',async({page})=>{
 const errors:string[]=[]
 page.on('pageerror',error=>errors.push(error.message))
 await page.route('**/api/v1/competitions',route=>route.fulfill({json:{data:[]}}))
 await page.goto('/')
 await expect(page.getByRole('heading',{name:'广金主场。 为这一局集结。'})).toBeVisible()
 await expect(page.locator('.g-identity-art')).toBeVisible()
 await expect(page.locator('.g-eyebrow')).toHaveText('赛事尚未公布')
 await expect(page.locator('.g-feature')).toContainText('赛程待公布')
 await expect(page.locator('.g-standings')).toContainText('积分待公布')
 await expect(page.locator('.g-fixture')).toHaveCount(0)
 await expect(page.locator('.g-team')).toHaveCount(0)
 await page.getByRole('button',{name:'查看比赛日'}).click()
 await expect(page.getByRole('button',{name:'赛果',exact:true})).toBeFocused()
 await page.getByRole('link',{name:'赛事首页',exact:true}).click()
 await expect(page).toHaveURL('http://localhost:5173/')
 await page.screenshot({path:'test-results/empty-home-desktop.png',fullPage:true})
 await page.setViewportSize({width:320,height:900})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await page.screenshot({path:'test-results/empty-home-mobile.png',fullPage:true})
 expect(errors).toEqual([])
})

test('published competition still supplies the homepage data',async({page})=>{
 const competition={id:'published',slug:'published',name:'已发布赛事',season:'2026',status:'ongoing'}
 await page.route('**/api/v1/competitions',route=>route.fulfill({json:{data:[competition]}}))
 await page.route('**/api/v1/competitions/published',route=>route.fulfill({json:{data:competition}}))
 await page.route('**/api/v1/competitions/published/home',route=>route.fulfill({json:{data:{competition,team_count:8,focus:null,matches:[],standings:[],stages:[]}}}))
 await page.goto('/')
 await expect(page.locator('.g-eyebrow')).toHaveText('已发布赛事')
 await expect(page.locator('.g-strip')).toContainText('8 支队伍')
 await expect(page.getByRole('link',{name:'完整积分与晋级说明 ↗'})).toHaveAttribute('href','/competitions/published/standings')
})

test('homepage load failure preserves branding and shows retry',async({page})=>{
 await page.route('**/api/v1/competitions',route=>route.fulfill({status:503,json:{error:{message:'赛事服务暂不可用'}}}))
 await page.goto('/')
 await expect(page.getByRole('alert')).toContainText('赛事服务暂不可用')
 await expect(page.getByRole('button',{name:'重试',exact:true})).toBeVisible()
 await expect(page.getByRole('heading',{name:'广金主场。 为这一局集结。'})).toBeVisible()
 await expect(page.locator('.g-eyebrow')).toHaveText('赛事信息暂不可用')
})
