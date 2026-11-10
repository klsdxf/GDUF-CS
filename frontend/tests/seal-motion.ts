import {expect,type Locator,type Page} from '@playwright/test'

/** Check handler-written properties so entrance animations cannot produce a false pass. */
export async function expectSealMotion(page:Page,scope:Locator=page.locator('main')){
 const scene=scope.locator('.v5-seal-scene'),object=scope.locator('.v5-seal-object')
 await expect(scene).toBeVisible()
 expect(await page.evaluate(()=>matchMedia('(hover:hover) and (pointer:fine)').matches)).toBeTruthy()
 await scene.scrollIntoViewIfNeeded()
 await expect.poll(()=>scene.evaluate(el=>el.getAnimations().every(a=>a.playState==='finished'))).toBeTruthy()
 const box=(await scene.boundingBox())!
 const angle=(name:string)=>object.evaluate((el,name)=>parseFloat((el as HTMLElement).style.getPropertyValue(name)),name)
 await scene.hover({position:{x:box.width*.25,y:box.height*.25}})
 await expect.poll(()=>angle('--seal-rx')).toBeCloseTo(10,0)
 await expect.poll(()=>angle('--seal-ry')).toBeCloseTo(-17.5,0)
 await scene.hover({position:{x:box.width*.75,y:box.height*.75}})
 await expect.poll(()=>angle('--seal-rx')).toBeCloseTo(4,0)
 await expect.poll(()=>angle('--seal-ry')).toBeCloseTo(-8.5,0)
 await page.mouse.move(0,0)
 await expect.poll(()=>object.evaluate(el=>[el.style.getPropertyValue('--seal-rx'),el.style.getPropertyValue('--seal-ry')])).toEqual(['',''])
}
