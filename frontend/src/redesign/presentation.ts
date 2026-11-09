export const escape=(value:unknown)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))
export function matchStatus(m:any){
 const names:Record<string,string>={unscheduled:'待安排',scheduled:'待开始',ongoing:'进行中',completed:'已结束',postponed:'已延期',cancelled:'已取消'}
 if(m.confirmed&&['forfeit','technical'].includes(m.result?.result_type))return '已结束 · '+(m.result.result_type==='forfeit'?'弃权':'技术判负')
 return names[m.status]||'状态待确认'
}
export const dayKey=(value:string)=>value&&Number.isFinite(Date.parse(value))?new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date(value)):''
export function nextMatchday(matches:any[],now=new Date()){
 const timed=matches.filter(m=>dayKey(m.scheduled_at)).sort((a,b)=>Date.parse(a.scheduled_at)-Date.parse(b.scheduled_at)||String(a.id).localeCompare(String(b.id)))
 const target=timed.find(m=>m.status==='ongoing')||timed.find(m=>m.status==='scheduled'&&dayKey(m.scheduled_at)>=dayKey(now.toISOString()))
 return target?timed.filter(m=>dayKey(m.scheduled_at)===dayKey(target.scheduled_at)&&['scheduled','ongoing','completed'].includes(m.status)):[]
}
export function liveUrl(value:unknown){try{const u=new URL(String(value));return u.protocol==='https:'&&!u.username&&!u.password&&/(^|\.)bilibili\.com$/.test(u.hostname)?u.href:''}catch{return ''}}
export function resolveLiveAction(rows:any[]=[],state='ready',matchId=''){
 if(state==='loading'||state==='error')return {kind:state,label:state==='loading'?'直播信息加载中':'直播信息暂不可用',tone:'muted',url:''}
 const actions=rows.map(r=>({r,url:liveUrl(r.status==='replay'?r.replay_url:r.room_url)})).filter(x=>x.url&&['live','replay','offline'].includes(x.r.status)).sort((a,b)=>Number(b.r.match_id===matchId&&!!matchId)-Number(a.r.match_id===matchId&&!!matchId)||['live','replay','offline'].indexOf(a.r.status)-['live','replay','offline'].indexOf(b.r.status)||String(a.r.id).localeCompare(String(b.r.id)))
 const a=actions[0];return a?{kind:a.r.status,label:a.r.status==='live'?'观看直播':a.r.status==='replay'?'观看回放':'直播安排',tone:a.r.status==='live'?'primary':'secondary',url:a.url}:{kind:'empty',label:'直播信息待公布',tone:'muted',url:''}
}
export function classifyPublicRoute(path:string,demo=false){
 const parts=path.split('/').slice(1)
 if(['/', '/competitions','/announcements'].includes(path))return true
 if(/^\/(matches|announcements)\/[^/]+$/.test(path))return !demo||(parts[0]==='matches'?['featured','upcoming','upcoming-2'].includes(parts[1]!):/^[0-2]$/.test(parts[1]!))
 if(parts[0]!=='competitions'||!parts[1]||(demo&&!['autumn','spring','archive'].includes(parts[1])))return false
 if(parts.length===2)return true
 if(parts.length===3)return ['schedule','standings','teams','rules','announcements','live'].includes(parts[2]!)
 return parts.length===4&&parts[2]==='teams'&&!!parts[3]&&(!demo||(parts[1]==='autumn'&&/^[0-7]$/.test(parts[3])))
}
export const notFound=()=>'<section class="empty-state"><h1>页面不存在</h1><p>内容不存在或尚未公开。</p><a class="btn" href="/">返回首页</a> <a href="/competitions">浏览赛事</a></section>'
export function updatePageMeta(path:string,missing=false,title=''){
 document.title=(missing?'页面不存在':title||(path==='/'?'首页':path.startsWith('/matches/')?'比赛详情':path.startsWith('/announcements')?'赛事公告':'赛事'))+' · GDUF CS'
 const meta=(name:string,value:string,property=false)=>{const key=property?'property':'name';let el=document.head.querySelector<HTMLMetaElement>(`meta[${key}="${name}"]`);if(!el){el=document.createElement('meta');el.setAttribute(key,name);document.head.append(el)}el.content=value}
 const description=missing?'内容不存在或尚未公开。':'广东金融学院 CS2 赛事、赛程、战队与正式赛果。'
 meta('description',description);meta('og:title',document.title,true);meta('og:description',description,true)
 const canonical='https://www.gdufcs.fun'+path
 let link=document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');if(!link){link=document.createElement('link');link.rel='canonical';document.head.append(link)}link.href=canonical;meta('og:url',canonical,true)
 if(missing)meta('robots','noindex');else document.head.querySelector('meta[name="robots"]')?.remove()
}

export function responsiveImages(html:string){return html.replace(/<img([^>]*?)src="(\/redesign\/assets\/cs2-[123])\.jpg"([^>]*?)>/g,(_,before,src,after)=>{const hero=before.includes('hero-photo');after=after.replace(/\s(?:loading|decoding|fetchpriority)="[^"]*"/g,'');return `<img${before}src="${src}-960.webp"${after} srcset="${src}-480.webp 480w, ${src}-960.webp 960w, ${src}-1440.webp 1440w" sizes="${hero?'(max-width: 760px) 100vw, 70vw':'(max-width: 760px) 90vw, 50vw'}" ${hero?'fetchpriority="high"':'loading="lazy"'} decoding="async">`})}

export function renderMatchday(matches:any[],scheduleUrl:string,stages:any[]=[],now=new Date()){const rows=nextMatchday(matches,now);return `<section class="match-ribbon"><div class="ribbon-label"><strong>下一比赛日 · 共 ${rows.length} 场</strong><a href="${escape(scheduleUrl)}">完整赛程 →</a></div><div class="ribbon-games">${rows.map(m=>`<a class="ribbon-game" href="/matches/${escape(m.id)}"><div class="ribbon-date">${escape(new Date(m.scheduled_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))}</div><div class="ribbon-pair">${escape(m.teams[0]?.name)||'待定'} vs ${escape(m.teams[1]?.name)||'待定'}<br><span class="ribbon-format">${escape(stages.find(s=>s.id===m.stage_id)?.name||'比赛')} · ${escape(m.group?m.group+'组':m.code)} · BO${escape(m.best_of)} · ${escape(matchStatus(m))}</span></div>↗</a>`).join('')||`<p class="ribbon-game">${matches.some(m=>['unscheduled','scheduled'].includes(m.status)&&!dayKey(m.scheduled_at))?'开赛时间待安排':'暂无后续赛程'}</p>`}</div></section>`}
