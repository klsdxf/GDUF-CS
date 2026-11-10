import template from './template.html?raw'
import {escape as e} from '../redesign/presentation'
export type Team={team_id:string;name:string;english_name:string;emblem_text:string;logo_url?:string|null;poster_title_lines:string[]}
export type ResultDTO={schema_version:string;competition:any;display:any;champion:Team&{seal_mode?:string};placements:any[];champion_path:any[];final_match:any;prizes:any[];allocations:any[];presenting_partner:any;official_partners:any[];support_totals:Record<string,number>;release?:any}
export const rank=(p:any)=>p.rank_from===p.rank_to?String(p.rank_from).padStart(2,'0'):`${p.rank_from}–${p.rank_to}`
export const score=(m:any)=>m?.result_type==='normal'?`${m.wins_a} : ${m.wins_b}`:m?.result_type==='forfeit'?'弃权':'技术判负'
export const teamName=(d:ResultDTO,id:string)=>d.placements.find(p=>p.team_id===id)?.team.name||'待定'
export function awards(d:ResultDTO,p:any){return d.allocations.filter(a=>a.placement_id===p.id).map(a=>({a,z:d.prizes.find(z=>z.id===a.prize_id)})).filter(x=>x.z)}
let sealSequence=0
export type ResultRenderOptions={visualVariant:'v6';context:'public'|'admin-preview'|'offline'|'reference'}
export function render(d:ResultDTO,selected=0,options:ResultRenderOptions={visualVariant:'v6',context:'public'}){
 const reference=options.context==='reference'
 const root=document.createElement('div');root.innerHTML=template
 const one=(s:string)=>root.querySelector<HTMLElement>(s)!
 const text=(s:string,v:any)=>{one(s).textContent=String(v??'')}
 const html=(s:string,v:string)=>{one(s).innerHTML=v}
 const title=d.display.edition_label||d.competition.name,c=d.champion,final=d.final_match,partner=d.presenting_partner
 const brand=partner?.english_name||partner?.name||'',brandFull=[partner?.english_name,partner?.name].filter(Boolean).join(' / ')
 text('.v5-season',title+(reference?' · 赛后示例':''))
 const lines=c.poster_title_lines.length?c.poster_title_lines:[c.english_name||c.name]
 if(!reference&&lines.length>1)one('.v4-type h3').setAttribute('data-poster-lines',String(lines.length))
 html('.v4-type h3',`${e(lines[0])}${lines.length>1?'<br><span>'+e(lines[1])+'</span>':''}<b>${e(c.name)}</b>`)
 if(Math.max(...lines.map(x=>x.length))>12)one('.v4-type h3').style.fontSize=`clamp(50px,${Math.max(4,10.3*12/Math.max(...lines.map(x=>x.length)))}vw,150px)`
 html('.v4-champ-meta',`<span>${e(title)}冠军${reference?' · 示例':''}</span><span>决赛 <b>${e(score(final).replace(' : ','—'))}</b> ${e(teamName(d,final.a_team_id===c.team_id?final.b_team_id:final.a_team_id))}</span>`)
 const seal=one('.v5-seal-scene');seal.setAttribute('aria-label',c.name+' 冠军纪念章')
 seal.querySelectorAll('text,textPath').forEach(el=>{
  if(el.children.length)return
  const t=el.textContent?.trim()
  if(t==='MF'){el.textContent=c.emblem_text;el.setAttribute('font-size',String(c.emblem_text.length<=2?150:Math.max(42,300/c.emblem_text.length)))}
  if(t==='KAPOK FIVE')el.textContent=c.english_name||c.name
  if(t?.includes('FALL 2026'))el.textContent=t.replace('FALL 2026',d.display.seal_edition_label||d.competition.season)
  if(t==='001')el.textContent=d.display.seal_serial||''
 })
 if(c.seal_mode==='team_logo'&&c.logo_url){
  seal.querySelectorAll('text').forEach(el=>{if(el.textContent?.trim()===c.emblem_text)el.remove()})
  const img=document.createElementNS('http://www.w3.org/2000/svg','image');img.setAttribute('href',c.logo_url);img.setAttribute('x','205');img.setAttribute('y','220');img.setAttribute('width','190');img.setAttribute('height','130');img.setAttribute('preserveAspectRatio','xMidYMid meet');seal.querySelector('svg')!.append(img)
 }
 const prefix='seal-'+(++sealSequence)+'-'
 seal.querySelectorAll('[id]').forEach(el=>{const old=el.id;el.id=prefix+old;seal.querySelectorAll('*').forEach(child=>{for(const attr of Array.from(child.attributes)){if(attr.value.includes('#'+old))child.setAttribute(attr.name,attr.value.replaceAll('#'+old,'#'+prefix+old))}})})
 html('.v5-seal-caption',`<span>GDUF CS / CHAMPIONS EDITION</span><span>NO. ${e(d.display.seal_serial)} — ${e(d.competition.season)}</span>`)
 html('.v4-win-bottom>span:nth-child(2)',`GRAND FINAL<b>${e(teamName(d,final.a_team_id))} <em>${e(score(final))}</em> ${e(teamName(d,final.b_team_id))}</b>`)
 one('.v4-win-bottom button').dataset.match=final.id;one('.v4-win-bottom button').removeAttribute('data-dialog')
 html('.v4-runners',d.placements.filter(p=>p.rank_from===2||p.rank_from===3).map(p=>{const t=p.team,items=awards(d,p).filter(x=>x.z.category==='equipment');return `<article><span class="v4-big-place">${rank(p)}</span><div class="v4-runner-name"><small>${p.rank_from===2?'RUNNER-UP / 亚军':p.rank_to>3?'THIRD PLACE / 并列季军':'THIRD PLACE / 季军'}</small><h3>${e(t.name)}</h3><span>${e(t.english_name)}</span></div><div class="v4-runner-prize"><span>${e(items.map(x=>x.z.name).join(' / ')||'奖品待公布')}</span><small>${items.map(x=>`全队 ${x.a.quantity} ${e(x.z.unit)}`).join(' / ')}</small></div><span class="v4-runner-code" aria-hidden="true">${e(t.emblem_text)}</span></article>`}).join(''))
 html('.v4-road',`<div class="v4-road-title"><span>THE RUN</span><h3>冠军之路</h3></div>`+d.champion_path.map(m=>`<button data-match="${e(m.id)}"><small>${e(m.label)} / BO${m.best_of}</small><span>${e(teamName(d,m.a_team_id))} <b>${e(score(m))}</b> ${e(teamName(d,m.b_team_id))}</span><i>↗</i></button>`).join(''))
 text('#team-count',d.placements.length+(reference?' 支示例队伍':' 支队伍'))
 html('.results-table tbody',d.placements.map(p=>{const t=p.team,items=awards(d,p).sort((a,b)=>Number(a.z.category==='commemorative')-Number(b.z.category==='commemorative'));const reward=items.map(({z,a})=>z.category==='commemorative'&&items.length>1?'纪念徽章':`${e(z.name)} × ${a.quantity}`).join(' + ');const providers=[...new Set(items.map(x=>[partner,...d.official_partners].find(s=>s?.id===x.z.provider_partner_id)?.english_name||[partner,...d.official_partners].find(s=>s?.id===x.z.provider_partner_id)?.name||''))];return `<tr data-team="${e(t.name+t.english_name)}"><td>${rank(p)}</td><td><${reference?'span':'a'} ${reference?'':`href="/competitions/${e(d.competition.slug)}/teams/${e(t.team_id)}"`} class="table-identity"><span class="result-badge">${t.logo_url?`<img src="${e(t.logo_url)}" alt="" style="width:100%;height:100%;object-fit:contain">`:e(t.emblem_text)}</span><div><strong>${e(t.name)}</strong><small>${e(t.english_name)}</small></div></${reference?'span':'a'}></td><td>${reward||'奖品待公布'}</td><td>${providers.map(e).join(' / ')}</td></tr>`}).join(''))
 if(!reference){text('.v4-title>div>span',d.competition.season);text('.v4-title>p','赛事排名');text('.results-table caption','完整最终名次与奖励');html('.results-foot','<span>以正式发布版本为准</span><span>'+e(title)+'</span>');text('.v4-section-head>div>span','THE FINAL RANKINGS')}
 const podium=d.placements.filter(p=>p.rank_from<=3),p=podium[selected]||podium[0],items=awards(d,p).filter(x=>x.z.category==='equipment'),z=items[0]?.z,a=items[0]?.a
 text('.v4-award-by','奖品支持 / '+[partner?.english_name,partner?.name].filter(Boolean).join(' ')+(reference?' · 虚构品牌':''))
 text('#product-model',z?.model_code||'—');text('#product-index',String(selected+1).padStart(2,'0')+' / '+String(podium.length).padStart(2,'0'))
 text('#product-title',z?.name||'该名次奖品待公布');text('#product-team',p.team.name)
 const label=p.rank_from===1?'冠军':p.rank_from===2?'亚军':'季军'
 text('#product-description',reference&&z?`${label}全队装备。每位队员 1 ${z.unit}，共 ${a.quantity} ${z.unit}。`:items.map(({z,a})=>`${z.name}：全队 ${a.quantity} ${z.unit}。${z.description||''}`).join(' '))
 text('.v4-product-brand',brandFull);text('.v4-product-art-note',brand+' / EQUIPMENT SERIES')
 const visual=one('#product-visual');visual.setAttribute('aria-label',(z?.name||'奖品待公布')+'示意插画')
 if(z?.image_url){visual.replaceWith(Object.assign(document.createElement('img'),{src:z.image_url,alt:z.name,id:'product-visual'}))}
 else one('#product-use').setAttribute('href',z?.builtin_illustration_key?'#'+z.builtin_illustration_key:'')
 html('.v4-prize-tabs',podium.map((p,i)=>`<button role="tab" id="award-tab-${i}" aria-controls="award-panel" aria-selected="${i===selected}" tabindex="${i===selected?0:-1}" data-award="${i}">${rank(p)} ${p.rank_from===1?'冠军':p.rank_from===2?'亚军':p.rank_to>3?'并列季军':'季军'}</button>`).join(''))
 one('#award-panel').setAttribute('aria-labelledby','award-tab-'+selected)
 one('#product-detail').removeAttribute('data-dialog');one('#product-detail').dataset.prize=p.id
 if(!reference){html('.v4-gift','<span>＋</span><p><b>纪念支持</b>'+d.support_totals.commemorative+' 枚纪念品</p>');text('.v4-equipment-note','前三名全队装备支持，按本届发布资料分配。')}
 text('.v4-sponsor-wordmark strong',partner?.english_name||partner?.name);text('.v4-sponsor-wordmark>span',partner?.name)
 one('.v4-sponsor-wordmark').setAttribute('aria-label',brandFull)
 if(partner?.logo_url){one('.v4-sponsor-wordmark svg').replaceWith(Object.assign(document.createElement('img'),{src:partner.logo_url,alt:partner.name}))}
 else if(partner?.builtin_mark_key!=='nexcore')one('.v4-sponsor-wordmark svg').remove()
 text('.v4-sponsor-bottom>p',partner?.introduction||partner?.description||partner?.support_description||'')
 html('.v4-sponsor-bottom>div',`<span><b>${d.support_totals.equipment}</b> 件获奖外设</span><span><b>${d.support_totals.commemorative}</b> 枚参赛徽章</span>`)
 html('.official-partners',d.official_partners.map(x=>`<div>${x.logo_url?`<img src="${e(x.logo_url)}" alt="${e(x.name)}">`:''}<b>${e(x.english_name||x.name)}<span>${e(x.name)}</span></b><small>${e(x.category)}</small></div>`).join(''))
 if(!reference){text('.v4-sponsor-line>span:last-child','首席赞助商');text('.official-caption>span:last-child','本届赛事合作伙伴');text('.design-note','本页展示已发布最终排名与赛事合作资料。')}
 return root.innerHTML
}
