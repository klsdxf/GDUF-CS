import {test,expect} from '@playwright/test'
test.use({baseURL:'http://127.0.0.1:5176'})
test('API retry recovers without invented demo results',async({page})=>{
 let failed=true;await page.route('**/api/v1/competitions',r=>failed?r.fulfill({status:503,json:{error:{message:'服务暂不可用'}}}):r.fulfill({json:{data:[]}}))
 await page.goto('/');await expect(page.getByRole('alert')).toContainText('服务暂不可用');failed=false;await page.getByRole('button',{name:'重试',exact:true}).click();await expect(page.locator('.hero')).toContainText('赛事尚未公布');await expect(page.locator('.event-card')).toHaveCount(0);await expect(page.getByRole('alert')).toHaveCount(0)
})
