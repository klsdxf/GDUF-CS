import {test,expect} from '@playwright/test'
import {readFileSync,mkdirSync} from 'node:fs'
import {expectSealMotion} from './seal-motion'

test.skip(process.env.BACKEND_DATA_E2E!=='1','requires the isolated dataset server')

test('backend initialization, editable data, four-team V6 results and offline export',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/');await expect(page.locator('.hero')).toContainText('赛事尚未公布')
 await page.goto('/admin/login');await page.getByLabel('账号',{exact:true}).fill('dataset-admin');await page.getByLabel('密码',{exact:true}).fill('dataset-acceptance-only!');await page.getByRole('button',{name:'登录',exact:true}).click()
 await page.getByRole('button',{name:'测试数据初始化',exact:true}).click()
 await page.getByRole('button',{name:'预览测试数据',exact:true}).click();await expect(page.locator('main')).toContainText("Poppin'Party")
 await expect(page.locator('main')).toContainText('补充的合成测试对局')
 await page.getByRole('button',{name:'确认提交测试数据',exact:true}).click();await expect(page.locator('main')).toContainText('测试数据已保存')
 await page.getByRole('button',{name:'参赛名单',exact:true}).click();await expect(page.locator('.el-table')).toContainText("Poppin'Party");await expect(page.locator('main')).toContainText('示例／测试数据')
 await page.getByRole('button',{name:'公告管理',exact:true}).click();await page.getByRole('button',{name:'编辑 / 下架',exact:true}).first().click()
 await page.getByLabel('正文（纯文本）').fill('后端同步更新已验证。');const saved=page.waitForResponse(r=>r.url().includes('/api/v1/admin/announcements/')&&r.request().method()==='PATCH');await page.getByRole('button',{name:'保存公告',exact:true}).click();expect((await saved).ok()).toBeTruthy();await expect(page.getByLabel('正文（纯文本）')).toHaveValue('')
 const pub=await page.context().newPage();pub.on('pageerror',e=>errors.push(e.message));await pub.setViewportSize({width:1280,height:900})
 await pub.goto('/');await expect(pub.locator('.hero h1')).toHaveText('AUTUMN2026');await expect(pub.locator('.event-card')).toHaveCount(3)
 await pub.locator('.news-row').first().click();await expect(pub.locator('dialog')).toContainText('后端同步更新已验证。');await pub.keyboard.press('Escape')
 await pub.goto('/competitions/autumn');await expect(pub.locator('.event-facts')).toContainText('4 支队伍');await expect(pub.locator('.event-facts')).toContainText('进行中')
 await pub.goto('/results');await expect(pub.locator('.v4-type h3')).toContainText("Poppin'Party");await expect(pub.locator('.results-table tbody tr')).toHaveCount(4);await expect(pub.locator('.v4-road button')).toHaveCount(2)
 await expect(pub.locator('body')).not.toContainText('示例');await expect(pub.locator('body')).not.toContainText('虚构');await expect(pub.locator('.results-partner')).toHaveCount(5);await expect(pub.locator('.v4-gift')).toContainText('20');await expect(pub.locator('.v4-equipment-note')).toContainText('15')
 await expectSealMotion(pub)
 await pub.locator('.v4-road button').first().click();await expect(pub.locator('#result-dialog')).toContainText('暂无逐图成绩');await expect(pub.locator('#result-dialog a')).toHaveCount(0);await pub.keyboard.press('Escape')
 await pub.locator('#search').fill("Poppin'Party");await expect(pub.locator('.results-table tbody tr:visible')).toHaveCount(1);await pub.locator('#search').fill('')
 await pub.locator('#award-tab-2').click();await expect(pub.locator('#product-title')).toHaveText('M4 无线鼠标')
 const pending=pub.waitForEvent('download');await pub.getByRole('button',{name:'下载排名页面',exact:true}).click();const download=await pending
 mkdirSync('../reports/backend-test-data',{recursive:true});const path='../reports/backend-test-data/four-team-results.html';await download.saveAs(path)
 const html=readFileSync(path,'utf8');expect(html).toContain("Poppin");expect(html).not.toContain('示例数据');expect(html).not.toContain('steam_id')
 const offline=await page.context().newPage();await offline.route('**/*',r=>r.abort());await offline.setContent(html);await offline.locator('#award-tab-1').click();await expect(offline.locator('#product-title')).toHaveText('K75 机械键盘');await offline.close()
 await page.bringToFront();await page.getByRole('button',{name:'最终排名与奖励',exact:true}).click();await expect(page.locator('main')).toContainText('测试排名')
 await page.getByRole('button',{name:'校验发布条件',exact:true}).click();await expect(page.locator('main')).toContainText('可发布')
 await page.getByPlaceholder('发布 / 修订 / 撤回原因').fill('浏览器测试重新发布');await page.getByRole('button',{name:'发布测试排名',exact:true}).click();await expect(page.locator('main')).toContainText('已有公开版本')
 await pub.goto('/results/autumn');await expect(pub.locator('.v4-type h3')).toContainText("Poppin'Party")
 for(const width of [1920,1600,1599,1280,1051,1050,768,761,760,390,381,380,360,320]){
  await pub.setViewportSize({width,height:900});await pub.evaluate(()=>document.fonts.ready)
  expect(await pub.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),String(width)+' overflow').toBeTruthy()
  await pub.locator('main').screenshot({path:`../reports/backend-test-data/results-${width}.png`,animations:'disabled'})
 }
 expect(errors).toEqual([])
})
