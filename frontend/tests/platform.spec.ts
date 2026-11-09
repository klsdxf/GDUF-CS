import {test,expect} from '@playwright/test'
test('public shell keeps keyboard navigation and management access',async({page})=>{
 await page.goto('/');await page.locator('.header').waitFor();expect(await page.locator('.header').evaluate(el=>el.getBoundingClientRect().top)).toBe(0);await expect(page.getByRole('navigation',{name:'主导航',exact:true}).getByRole('link')).toHaveCount(6)
 await expect(page.getByRole('link',{name:'管理',exact:true})).toHaveAttribute('href','/admin/login')
 await page.locator('.news-row').first().click();await expect(page).toHaveURL(/announcements\/0$/);await expect(page.locator('dialog')).toBeVisible();await page.keyboard.press('Escape');await expect(page).toHaveURL(/\/$/)
 await expect(page.locator('.preview-bar')).toHaveCount(0);await expect(page.locator('#accent')).toHaveCount(0);await page.getByRole('link',{name:'赛事',exact:true}).click();await expect(page.locator('.public-site')).toHaveAttribute('data-theme','blue')
})
