import {test,expect} from '@playwright/test'
test.use({baseURL:'http://127.0.0.1:5176'})
const c={id:'real',slug:'history',name:'历史真实赛事',season:'2025',status:'archived',rules:'真实规则\n不得含假赛果',map_pool:['Mirage'],team_limit:8,organizer:'组织方'}
const t={id:'t1',name:'真实战队',code:'RL',members:[{nickname:'公开昵称',role:'正式',captain:true}]}
const m={id:'real-match',competition_id:'real',stage_id:'s1',code:'R1',group:'A',round:1,bracket:'upper',source_a:'',source_b:'',teams:[t,{...t,id:'t2',name:'对手'}],best_of:1,status:'completed',confirmed:true,scheduled_at:'2026-11-14T11:00:00Z',result:{wins_a:1,wins_b:0,result_type:'normal',maps:[{map_name:'Mirage',score_a:16,score_b:14,overtime:true}]}}
async function mock(page:any){await page.route('**/api/v1/**',(r:any)=>{const path=new URL(r.request().url()).pathname;let data:any=[];if(path==='/api/v1/competitions')data=[c];else if(['/api/v1/competitions/history','/api/v1/competitions/real'].includes(path))data=c;else if(path.endsWith('/home'))data={competition:c,matches:[m],focus:m,standings:[],stages:[]};else if(path.endsWith('/matches'))data=[m];else if(path.endsWith('/matches/real-match'))data=m;else if(path.endsWith('/stages'))data=[{id:'s1',name:'双败阶段',type:'double'}];else if(path.endsWith('/bracket'))data={matches:[m],edges:[],bye_sources:[{name:'轮空队伍',source:''}]};else if(path.endsWith('/standings'))data=[{team_id:'t1',name:'真实战队',group:'A',rank:1,wins:1,losses:0,points:3,map_diff:1,round_diff:2,unresolved:true}];else if(path.endsWith('/teams/t1'))data={...t,matches:[m]};else if(path.endsWith('/teams'))data=[t];else if(path.endsWith('/announcements/a1'))data={id:'a1',competition_id:'real',title:'真实公告',body:'<img src=x onerror=alert(1)>',publish_at:'2026-11-01T12:00:00Z'};else if(path.endsWith('/announcements'))data=[{id:'a1',title:'真实公告',publish_at:'2026-11-01T12:00:00Z'}];return r.fulfill({json:{data}})})}
test('API history, fixtures, standings, bracket, rosters, news, live and safe content',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await mock(page)
 for(const tab of ['','/schedule','/standings','/teams','/rules','/announcements','/live']){await page.goto('/competitions/history'+tab);await expect(page.locator('.public-site')).not.toContainText('木棉 FIVE');await expect(page.locator('main')).toContainText('历史真实赛事')}
 await expect(page.locator('dialog')).toContainText('暂无直播配置');await page.keyboard.press('Escape')
 await page.goto('/competitions/history/schedule?view=bracket');await expect(page.locator('.bracket-board')).toContainText('真实战队');await expect(page.locator('main')).toContainText('轮空队伍')
 await page.goto('/matches/real-match');await expect(page.locator('#map-report')).toContainText('加时');await expect(page.locator('.rosters')).toContainText('公开昵称')
 await page.goto('/competitions/history/teams/t1');await expect(page.locator('dialog')).toContainText('公开昵称')
 await page.goto('/announcements/a1');await expect(page.locator('dialog')).toContainText('<img src=x onerror=alert(1)>');await expect(page.locator('dialog img')).toHaveCount(0)
 expect(errors).toEqual([])
})
test('empty API and failures never fall back to demo',async({page})=>{
 await page.route('**/api/v1/**',r=>r.fulfill({json:{data:[]}}));await page.goto('/');await expect(page.locator('.hero')).toContainText('赛事尚未公布');await expect(page.locator('body')).not.toContainText('木棉');await expect(page.locator('.event-card')).toHaveCount(0)
 await page.route('**/api/v1/**',r=>r.fulfill({status:503,json:{error:{message:'赛事服务暂不可用'}}}));await page.reload();await expect(page.getByRole('alert')).toContainText('赛事服务暂不可用');await expect(page.getByRole('button',{name:'重试',exact:true})).toBeVisible();await expect(page.locator('body')).not.toContainText('木棉')
})
