import {test,expect} from '@playwright/test'
test.skip(process.env.RESULTS_LIVE_E2E!=='1','isolated result API server required')
test('real API administration previews publishes withdraws and republishes results',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/results');await expect(page.locator('main')).toContainText('最终排名待公布')
 await page.goto('/admin/login');await page.getByLabel('账号',{exact:true}).fill('results-admin');await page.getByLabel('密码',{exact:true}).fill('results-acceptance-only!');await page.getByRole('button',{name:'登录',exact:true}).click()
 await page.getByRole('button',{name:'最终排名与奖励',exact:true}).click();await expect(page.locator('main')).toContainText('暂无有效公开版本')
 await page.getByRole('button',{name:'内部预览',exact:true}).click();await expect(page.locator('.el-dialog .v4-type h3')).toContainText('战队0');await page.locator('.el-dialog__headerbtn').click()
 await page.getByRole('button',{name:'校验发布条件',exact:true}).click();await expect(page.locator('main')).toContainText('可发布');await page.getByPlaceholder('发布 / 修订 / 撤回原因').fill('浏览器验收正式发布');await page.getByRole('button',{name:'正式发布新版本',exact:true}).click();await expect(page.locator('main')).toContainText('已有公开版本')
 const result=await page.context().newPage();await result.goto('/results/test-cup');await expect(result.locator('.v4-type h3')).toContainText('战队0');await expect(result.locator('.v4-sponsor-wordmark')).toContainText('REAL');await expect(result.locator('main')).not.toContainText('木棉');await expect(result.locator('main')).not.toContainText('NEXCORE');await expect(result.locator('.results-table tr')).toHaveCount(5)
 await page.getByRole('button',{name:'撤回公开版本',exact:true}).click();await expect(page.locator('main')).toContainText('暂无有效公开版本');await result.reload();await expect(result.locator('main')).toContainText('页面不存在')
 await page.getByRole('button',{name:'校验发布条件',exact:true}).click();await page.getByRole('button',{name:'正式发布新版本',exact:true}).click();await expect(page.locator('main')).toContainText('已有公开版本');await result.reload();await expect(result.locator('.v4-type h3')).toContainText('战队0')
 expect(errors).toEqual([])
})
