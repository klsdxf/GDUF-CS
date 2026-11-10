import {test,expect} from '@playwright/test'
import {expectSealMotion} from './seal-motion'
test.skip(process.env.RESULTS_LIVE_E2E!=='1','isolated result API server required')
test('real API administration previews publishes withdraws and republishes results',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.setViewportSize({width:1280,height:900})
 await page.goto('/results');await expect(page.locator('main')).toContainText('最终排名待公布')
 await page.goto('/admin/login');await page.getByLabel('账号',{exact:true}).fill('results-admin');await page.getByLabel('密码',{exact:true}).fill('results-acceptance-only!');await page.getByRole('button',{name:'登录',exact:true}).click()
 await page.getByRole('button',{name:'最终排名与奖励',exact:true}).click();await expect(page.locator('main')).toContainText('暂无有效公开版本')
 for(let i=0;i<2;i++){
  await page.getByRole('button',{name:'内部预览',exact:true}).click();await expect(page.locator('.el-dialog .v4-type h3')).toContainText('战队0')
  await expectSealMotion(page,page.locator('.el-dialog'));await page.locator('.el-dialog__headerbtn').click()
  await expect(page.locator('.el-dialog .v5-seal-object')).toHaveCount(0)
 }
 await page.getByRole('button',{name:'校验发布条件',exact:true}).click();await expect(page.locator('main')).toContainText('可发布');await page.getByPlaceholder('发布 / 修订 / 撤回原因').fill('浏览器验收正式发布');await page.getByRole('button',{name:'正式发布新版本',exact:true}).click();await expect(page.locator('main')).toContainText('已有公开版本')
 const result=await page.context().newPage();result.on('pageerror',e=>errors.push(e.message))
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve})
 await result.route('**/api/v1/competitions/test-cup/results',async route=>{await gate;await route.continue()})
 await result.goto('/results/test-cup');await expect(result.getByRole('status')).toContainText('正在加载最终排名');release()
 await expect(result.locator('.v4-type h3')).toContainText('战队0');await expect(result.locator('.v4-sponsor-wordmark')).toContainText('REAL');await expect(result.locator('main')).not.toContainText('木棉');await expect(result.locator('main')).not.toContainText('NEXCORE');await expect(result.locator('.results-table tr')).toHaveCount(5)
 await expectSealMotion(result)
 await result.unrouteAll({behavior:'wait'})
 await result.route('**/api/v1/competitions/test-cup/results',route=>route.fulfill({status:503,json:{error:{message:'结果服务暂不可用'}}}))
 await result.reload();await expect(result.getByRole('alert')).toContainText('结果服务暂不可用')
 await result.unrouteAll({behavior:'wait'});await result.getByRole('button',{name:'重试',exact:true}).click();await expectSealMotion(result)
 await page.bringToFront();await page.getByRole('button',{name:'撤回公开版本',exact:true}).click();await expect(page.locator('main')).toContainText('暂无有效公开版本');await result.reload();await expect(result.locator('main')).toContainText('页面不存在')
 await page.getByRole('button',{name:'校验发布条件',exact:true}).click();await page.getByRole('button',{name:'正式发布新版本',exact:true}).click();await expect(page.locator('main')).toContainText('已有公开版本');await result.reload();await expect(result.locator('.v4-type h3')).toContainText('战队0')
 expect(errors).toEqual([])
})
