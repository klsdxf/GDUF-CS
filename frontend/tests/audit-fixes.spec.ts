import {test,expect} from '@playwright/test'
const widths=[360,390,768,1280]
for(const width of widths)test(`score and schedule retain information at ${width}`,async({page})=>{
 await page.setViewportSize({width,height:844});await page.goto('/matches/featured')
 const style=await page.locator('.match-hero').evaluate(el=>({color:getComputedStyle(el,'::before').color,z:getComputedStyle(el.querySelector('.match-final')!).zIndex}))
 expect(Math.abs(Number(style.color.match(/[\d.]+(?=\))/)?.[0])-.025)).toBeLessThan(.002);expect(Number(style.z)).toBeGreaterThan(0)
 await expect(page.locator('.match-final')).toContainText('2 : 1')
 await page.goto('/competitions/autumn/schedule');await page.locator('[data-day="14"]').click()
 await expect(page.locator('.fixture')).toHaveCount(2)
 for(const row of await page.locator('.fixture').all()){await expect(row.locator('.fixture-format')).toBeVisible();await expect(row.locator('.fixture-status')).toHaveText('待开始');expect(await row.locator('.fixture-time small').evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(11)}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 if(width===390)expect((await page.locator('.fixture').first().boundingBox())!.y+(await page.locator('.fixture').first().boundingBox())!.height).toBeLessThanOrEqual(844)
})
for(const width of [360,380,381,760,761,1050,1051])test(`all summary games visible ${width}`,async({page})=>{
 await page.setViewportSize({width,height:844});await page.goto('/');await expect(page.locator('.ribbon-game')).toHaveCount(2)
 for(const game of await page.locator('.ribbon-game').all()){await expect(game).toBeVisible();await expect(game.locator('.ribbon-format')).toBeVisible()}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
test('standings identity and source return; invalid routes recover metadata',async({page})=>{
 await page.goto('/competitions/autumn/standings?source=a');await page.locator('.inline-team').first().click();await expect(page).toHaveURL(/teams\/0$/);await page.keyboard.press('Escape');await expect(page).toHaveURL(/standings\?source=a$/)
 for(const path of ['/no-page','/competitions/unknown','/competitions/autumn/schedule/extra','/competitions/autumn/teams/-1','/competitions/autumn/teams/1.5','/announcements/NaN','/matches/absent']){await page.goto(path);await expect(page.locator('main h1')).toHaveText('页面不存在');await expect(page).toHaveTitle('页面不存在 · GDUF CS');await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content','noindex')}
 await page.locator('main a[href="/"]').click();await expect(page.locator('meta[name="robots"]')).toHaveCount(0)
})
test('shared presentation covers matchdays, states and stream URL validation',async({page})=>{
 await page.goto('/');const result=await page.evaluate(async()=>{
 const p=await import('/src/redesign/presentation.ts');const m=(id:string,time:string,status='scheduled')=>({id,scheduled_at:time,status})
 const rows=[m('late','2026-11-15T11:00:00Z'),m('2','2026-11-14T12:00:00Z'),m('1','2026-11-14T11:00:00Z'),m('3','2026-11-14T13:00:00Z'),m('old','2026-11-01T11:00:00Z')]
 return {days:[0,1,2,3].map(n=>p.nextMatchday(rows.filter(r=>['1','2','3'].slice(0,n).includes(r.id)),new Date('2026-11-09T00:00:00Z')).length),ids:p.nextMatchday(rows,new Date('2026-11-09T00:00:00Z')).map(r=>r.id),midnight:p.dayKey('2026-11-14T17:00:00Z'),states:['unscheduled','scheduled','ongoing','completed','postponed','cancelled','unknown'].map(status=>p.matchStatus({status})),forfeit:p.matchStatus({confirmed:true,result:{result_type:'forfeit'}}),urls:['https://live.bilibili.com/1','https://bilibili.com.evil.test/1','http://bilibili.com/1','https://user:pass@bilibili.com/1'].map(p.liveUrl),live:['live','replay','offline'].map(status=>p.resolveLiveAction([{id:'1',status,room_url:'https://live.bilibili.com/1',replay_url:'https://www.bilibili.com/video/1'}]).label)}
 });expect(result.days).toEqual([0,1,2,3]);expect(result.ids).toEqual(['1','2','3']);expect(result.midnight).toBe('2026-11-15');expect(result.states).toEqual(['待安排','待开始','进行中','已结束','已延期','已取消','状态待确认']);expect(result.forfeit).toBe('已结束 · 弃权');expect(result.urls.slice(1)).toEqual(['','','']);expect(result.live).toEqual(['观看直播','观看回放','直播安排'])
})
test('API stream failures do not hide page; resource errors have distinct semantics',async({page})=>{
 const c={id:'c',slug:'cup',name:'真实赛事',season:'2026',status:'scheduled'}
 await page.route('**/api/v1/**',r=>{const path=new URL(r.request().url()).pathname;if(path.endsWith('/live'))return r.fulfill({status:503,json:{error:{message:'直播服务失败'}}});if(path.endsWith('/matches/missing'))return r.fulfill({status:404,json:{error:{message:'不存在'}}});return r.fulfill({json:{data:path==='/api/v1/competitions'?[c]:path.endsWith('/cup')?c:path.endsWith('/home')?{matches:[],standings:[]}:[]}})})
 await page.goto('http://127.0.0.1:5176/');await expect(page.locator('.hero')).toContainText('真实赛事');await expect(page.locator('.watch')).toContainText('直播信息暂不可用');await page.locator('.watch').click();await expect(page.locator('dialog')).toContainText('重试直播信息')
 await page.goto('http://127.0.0.1:5176/matches/missing');await expect(page).toHaveTitle('页面不存在 · GDUF CS');await expect(page.locator('main h1')).toHaveText('页面不存在')
})

for(const width of [360,390,768,1280])test(`API readable score and complete matchday ${width}`,async({page})=>{
 await page.setViewportSize({width,height:844});await page.clock.install({time:new Date('2026-11-09T00:00:00Z')})
 const c={id:'cup',slug:'cup',name:'API 测试赛事',season:'2026',status:'ongoing',rules:'规则'},t={id:'t1',name:'很长的队伍名称 <img src=x onerror=alert(1)>',code:'A'},m={id:'m',competition_id:'cup',stage_id:'s',teams:[t,{id:'t2',name:'对手',code:'B'}],status:'scheduled',best_of:3,group:'A',scheduled_at:'2026-11-14T11:00:00Z',result:{},confirmed:false}
 let count=3,liveStatus='live'
 await page.route('**/api/v1/**',r=>{const path=new URL(r.request().url()).pathname;const rows=Array.from({length:count},(_,i)=>({...m,id:'m'+i}));return r.fulfill({json:{data:path==='/api/v1/competitions'?[c]:path.endsWith('/cup')?c:path.endsWith('/home')?{matches:rows,focus:null,standings:[],stages:[{id:'s',name:'小组赛'}]}:path.endsWith('/live')?[{id:'l',status:liveStatus,room_url:'https://live.bilibili.com/1',replay_url:'https://www.bilibili.com/video/1'}]:path.endsWith('/stages')?[{id:'s',name:'小组赛'}]:path.endsWith('/matches')?rows:path.includes('/matches/')?m:[]}})})
 for(count=0;count<=3;count++){await page.goto('http://127.0.0.1:5176/');await expect(page.locator('.ribbon-games')).toBeVisible();await expect(page.locator('.ribbon-games a')).toHaveCount(count);await expect(page.locator('.ribbon-games img')).toHaveCount(0)}
 for(liveStatus of ['live','replay','offline']){await page.reload();await expect(page.locator('.watch')).toContainText(liveStatus==='live'?'观看直播':liveStatus==='replay'?'观看回放':'直播安排')}
 await page.goto('http://127.0.0.1:5176/matches/m');await expect(page.locator('.match-team h2').first()).toHaveText(t.name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await page.goto('http://127.0.0.1:5176/competitions/cup/schedule');await expect(page.locator('.fixture-format').first()).toContainText('小组赛');await expect(page.locator('.fixture-status').first()).toHaveText('待开始')
})
