import template from './template.html?raw'
import {escape as e} from '../redesign/presentation'
import {partnerName, renderPartners, resultPartners, type ResultPartner} from './partners'
export type Team={team_id:string;name:string;english_name:string;emblem_text:string;logo_url?:string|null;poster_title_lines:string[]}
type AwardPlan={award_plan?:Record<string,string[]>;hide_award_quantities?:boolean;has_third_place?:boolean}
export type ResultDTO=AwardPlan&{schema_version:string;competition:any;display:any;champion:Team&{seal_mode?:string};placements:any[];champion_path:any[];final_match:any;prizes:any[];allocations:any[];partners?:ResultPartner[];presenting_partner?:ResultPartner|null;official_partners?:ResultPartner[];support_totals:Record<string,number>;release?:any;pending?:true}
export type PendingResult=AwardPlan&{pending:true;competition:{id:string;slug:string;name:string;season:string};partners:ResultPartner[];prizes?:any[]}
export const rank=(p:any)=>p.rank_from===p.rank_to?String(p.rank_from).padStart(2,'0'):`${p.rank_from}–${p.rank_to}`
export const score=(m:any)=>m?.result_type==='pending'?'? : ?':m?.result_type==='normal'?`${m.wins_a} : ${m.wins_b}`:m?.result_type==='forfeit'?'弃权':'技术判负'
export const teamName=(d:ResultDTO,id:string)=>d.placements.find(p=>p.team_id===id)?.team.name||'待定'
export const awardEligibility='获奖队伍的正式队员每人均可获得对应奖品'
export function awards(d:ResultDTO,p:any){
 const allocations=d.award_plan
  ?(d.award_plan[String(p.rank_from)]||[]).map(prize_id=>({prize_id}))
  :d.allocations.filter(a=>a.placement_id===p.id)
 return allocations.map(a=>({a,z:d.prizes.find(z=>z.id===a.prize_id)})).filter(x=>x.z)
}
export function awardPositions(d:ResultDTO){
 const positions=d.placements.filter(p=>d.award_plan?(d.award_plan[String(p.rank_from)]||[]).length:p.rank_from<=3)
 return d.pending&&!d.award_plan?positions.slice(0,3):positions
}
export function awardDetails(d:ResultDTO,p:any){
 const items=awards(d,p)
 return `<h2>${e(p.team.name)}</h2>`+items.map(({z,a})=>
  `<p>${e(z.name)}${d.hide_award_quantities?'':` × ${a.quantity} ${e(z.unit)}`}<br>${e(z.description||'')}</p>`).join('')
  +(d.hide_award_quantities?`<p>${awardEligibility}。</p>`:'')
}
let sealSequence=0
export type ResultRenderOptions={visualVariant:'v6';context:'public'|'admin-preview'|'offline'|'reference'}
export function pendingResultData({competition,partners,prizes,...plan}:PendingResult):ResultDTO {
 const team:Team={team_id:'',name:'待定',english_name:'',emblem_text:'?',poster_title_lines:['TBD']}
 const ranks=[[1,1],[2,2],...(plan.has_third_place?[[3,3],[4,4]]:[[3,4],[3,4]]),[5,8],[5,8],[5,8],[5,8]]
 const placements=ranks.map(([rank_from,rank_to],index)=>({id:'position-'+index,rank_from,rank_to,team}))
 const champion_path=['四分之一决赛','半决赛','决赛'].map(label=>({label,best_of:3,result_type:'pending'}))
 return {
  ...plan,pending:true,schema_version:'1.0',competition,partners,
  display:{edition_label:competition.name,seal_edition_label:'FALL '+competition.season},
  champion:team,placements,champion_path,final_match:champion_path[2],
  prizes:prizes||[],allocations:[],support_totals:{},
 }
}

export function render(d:ResultDTO,selected=0,options:ResultRenderOptions={visualVariant:'v6',context:'public'}){
 const reference=options.context==='reference'
 const pendingResults=d.pending===true
 const hideQuantities=d.hide_award_quantities===true
 const root=document.createElement('div');root.innerHTML=template
 const one=(s:string)=>root.querySelector<HTMLElement>(s)!
 const text=(s:string,v:any)=>{one(s).textContent=String(v??'')}
 const html=(s:string,v:string)=>{one(s).innerHTML=v}
 const title=d.display.edition_label||d.competition.name,c=d.champion,final=d.final_match,partner=d.presenting_partner
 const partners=resultPartners(d),partnerById=new Map(partners.map(item=>[item.id,item]))
 const pendingSponsor='待赞助'
 text('.v5-season',title+(reference?' · 赛后示例':''))
 const lines=c.poster_title_lines.length?c.poster_title_lines:[c.english_name||c.name]
 if(!reference&&lines.length>1)one('.v4-type h3').setAttribute('data-poster-lines',String(lines.length))
 html('.v4-type h3',`${e(lines[0])}${lines.length>1?'<br><span>'+e(lines[1])+'</span>':''}<b>${e(c.name)}</b>`)
 if(Math.max(...lines.map(x=>x.length))>12)one('.v4-type h3').style.fontSize=`clamp(50px,${Math.max(4,10.3*12/Math.max(...lines.map(x=>x.length)))}vw,150px)`
 html('.v4-champ-meta',`<span>${e(title)}冠军${pendingResults?'待定':reference?' · 示例':''}</span><span>决赛 <b>${e(score(final).replace(' : ','—'))}</b> ${e(teamName(d,final.a_team_id===c.team_id?final.b_team_id:final.a_team_id))}</span>`)
 const seal=one('.v5-seal-scene')
 const sealLabel=pendingResults?'冠军纪念章示例':c.name+' 冠军纪念章'
 seal.setAttribute('aria-label',sealLabel)
 if(pendingResults)seal.querySelector('svg')!.setAttribute('aria-label',sealLabel)
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
 html('.v5-seal-caption',`<span>GDUF CS / CHAMPIONS EDITION</span><span>${pendingResults?sealLabel:`NO. ${e(d.display.seal_serial)} — ${e(d.competition.season)}`}</span>`)
 html('.v4-win-bottom>span:nth-child(2)',`GRAND FINAL<b>${e(teamName(d,final.a_team_id))} <em>${e(score(final))}</em> ${e(teamName(d,final.b_team_id))}</b>`)
 const finalButton=one('.v4-win-bottom button')
 finalButton.removeAttribute('data-dialog')
 if(pendingResults){finalButton.setAttribute('disabled','');finalButton.textContent='逐图赛果待公布'}
 else finalButton.dataset.match=final.id
 const podium=d.placements.filter(p=>p.rank_from<=3)
 const runners=podium.filter(p=>p.rank_from===2||p.rank_from===3)
 const runnerCards=pendingResults?runners.slice(0,2):runners
 html('.v4-runners',runnerCards.map(p=>{const t=p.team,items=awards(d,p).filter(x=>x.z.category==='equipment');return `<article><span class="v4-big-place">${rank(p)}</span><div class="v4-runner-name"><small>${p.rank_from===2?'RUNNER-UP / 亚军':p.rank_to>3?'THIRD PLACE / 并列季军':'THIRD PLACE / 季军'}</small><h3>${e(t.name)}</h3><span>${e(t.english_name)}</span></div><div class="v4-runner-prize"><span>${e(items.map(x=>x.z.name).join(' / ')||'奖品待公布')}</span><small>${hideQuantities?'正式队员每人均可获得':items.map(x=>`全队 ${x.a.quantity} ${e(x.z.unit)}`).join(' / ')}</small></div><span class="v4-runner-code" aria-hidden="true">${e(t.emblem_text)}</span></article>`}).join(''))
 html('.v4-road',`<div class="v4-road-title"><span>THE RUN</span><h3>冠军之路</h3></div>`+d.champion_path.map(m=>`<button ${pendingResults?'disabled':`data-match="${e(m.id)}"`}><small>${e(m.label)} / BO${m.best_of}</small><span>${e(teamName(d,m.a_team_id))} <b>${e(score(m))}</b> ${e(teamName(d,m.b_team_id))}</span>${pendingResults?'':'<i>↗</i>'}</button>`).join(''))
 text('#team-count',d.placements.length+(reference?' 支示例队伍':' 支队伍'))
 html('.results-table tbody',d.placements.map(p=>{
  const t=p.team,items=awards(d,p).sort((a,b)=>Number(a.z.category==='commemorative')-Number(b.z.category==='commemorative'))
  const reward=items.map(({z,a})=>hideQuantities?e(z.name):z.category==='commemorative'&&items.length>1?'纪念徽章':`${e(z.name)} × ${a.quantity}`).join(' + ')
  const providerIds=new Set(items.map(({z})=>z.provider_partner_id))
  const providers=[...providerIds].flatMap(id=>{
   if(id===null)return hideQuantities?[]:[pendingSponsor]
   const sponsor=partnerById.get(id)
   return sponsor?[sponsor.english_name||sponsor.name]:[]
  })
  const identity=reference||pendingResults?'span':'a'
  return `<tr data-team="${e(t.name+t.english_name)}"><td>${rank(p)}</td><td><${identity} ${identity==='a'?`href="/competitions/${e(d.competition.slug)}/teams/${e(t.team_id)}"`:''} class="table-identity"><span class="result-badge">${t.logo_url?`<img src="${e(t.logo_url)}" alt="" style="width:100%;height:100%;object-fit:contain">`:e(t.emblem_text)}</span><div><strong>${e(t.name)}</strong><small>${e(t.english_name)}</small></div></${identity}></td><td>${reward||(d.award_plan?'—':'奖品待公布')}</td><td>${providers.map(e).join(' / ')||(d.award_plan?'—':pendingResults?'待公布':'')}</td></tr>`
 }).join(''))
 if(!reference){text('.v4-title>div>span',d.competition.season);text('.v4-title>p','赛事排名');text('.results-table caption','完整最终名次与奖励');html('.results-foot','<span>以正式发布版本为准</span><span>'+e(title)+'</span>');text('.v4-section-head>div>span','THE FINAL RANKINGS')}
 if(pendingResults){
  text('.v4-title>p','赛果待公布')
  one('.rank-search').hidden=true
 }
 const awardRanks=awardPositions(d)
 const p=awardRanks[selected]||awardRanks[0],items=awards(d,p).filter(x=>x.z.category==='equipment'),z=items[0]?.z,a=items[0]?.a
 const productProvider=reference?partner:partnerById.get(z?.provider_partner_id)
 const brand=productProvider?.english_name||productProvider?.name||''
 const pending=!hideQuantities&&z?.provider_partner_id===null
 const brandFull=reference?[partner?.english_name,partner?.name].filter(Boolean).join(' / '):pending?pendingSponsor:partnerName(productProvider)
 const awardedPrizes=new Set(d.award_plan?Object.values(d.award_plan).flat():d.allocations.map(a=>a.prize_id))
 const equipmentProviders=new Set(d.prizes.filter(z=>z.category==='equipment'&&awardedPrizes.has(z.id)).map(z=>z.provider_partner_id))
 const equipmentNames=partners.filter(s=>equipmentProviders.has(s.id)).map(partnerName)
 if(!hideQuantities&&equipmentProviders.has(null))equipmentNames.push(pendingSponsor)
 const awardBy=reference?[partner?.english_name,partner?.name].filter(Boolean).join(' ')+' · 虚构品牌':equipmentNames.join('、')
 text('.v4-award-by',awardBy?'奖品支持 / '+awardBy:'')
 text('#product-model',z?.model_code||(hideQuantities&&z?'':pendingResults?'?':'—'));text('#product-index',String(selected+1).padStart(2,'0')+' / '+String(awardRanks.length).padStart(2,'0'))
 text('#product-title',z?.name||'该名次奖品待公布');text('#product-team',p.team.name)
 const label=p.rank_from===1?'冠军':p.rank_from===2?'亚军':'季军'
 text('#product-description',hideQuantities?`${awardEligibility}。`:reference&&z?`${label}全队装备。每位队员 1 ${z.unit}，共 ${a.quantity} ${z.unit}。`:items.map(({z,a})=>`${z.name}：全队 ${a.quantity} ${z.unit}。${z.description||''}`).join(' '))
 text('.v4-product-brand',brandFull);text('.v4-product-art-note',pending?pendingSponsor:brand?brand+' / EQUIPMENT SERIES':'')
 const visual=one('#product-visual');visual.setAttribute('aria-label',(z?.name||'奖品待公布')+'示意插画')
 if(z?.image_url){visual.replaceWith(Object.assign(document.createElement('img'),{src:z.image_url,alt:z.name,id:'product-visual'}))}
 else one('#product-use').setAttribute('href',z?.builtin_illustration_key?'#'+z.builtin_illustration_key:'')
 html('.v4-prize-tabs',awardRanks.map((p,i)=>`<button role="tab" id="award-tab-${i}" aria-controls="award-panel" aria-selected="${i===selected}" tabindex="${i===selected?0:-1}" data-award="${i}">${rank(p)} ${p.rank_from===1?'冠军':p.rank_from===2?'亚军':p.rank_from===4?'第四名':p.rank_to>3?'并列季军':'季军'}</button>`).join(''))
 one('#award-panel').setAttribute('aria-labelledby','award-tab-'+selected)
 one('#product-detail').removeAttribute('data-dialog');one('#product-detail').dataset.prize=p.id
 if(pendingResults&&!items.length)one('#product-detail').remove()
 if(!reference){
  one('.v4-equipment').classList.add('results-equipment')
  if(hideQuantities){
   if(items.length>1)html('.v4-gift',`<span>＋</span><p><b>四强加赠</b>${items.slice(1).map(({z})=>e(z.name)).join('、')}</p>`)
   else one('.v4-gift').remove()
  }else html('.v4-gift','<span>＋</span><p><b>纪念支持</b>'+(pendingResults?'待公布':d.support_totals.commemorative+' 枚纪念品')+'</p>')
  text('.v4-equipment-note',hideQuantities?'插图为奖品类别示意。':pendingResults?'奖品以本届正式公告为准。':d.support_totals.equipment+' 件获奖外设，按本届发布资料分配。')
  const legacyMark=one('.v4-sponsor-wordmark svg').outerHTML
  one('#partners').outerHTML=renderPartners(partners,legacyMark)
  return root.innerHTML
 }
 text('.v4-sponsor-wordmark strong',partner?.english_name||partner?.name);text('.v4-sponsor-wordmark>span',partner?.name)
 one('.v4-sponsor-wordmark').setAttribute('aria-label',brandFull)
 if(partner?.logo_url){one('.v4-sponsor-wordmark svg').replaceWith(Object.assign(document.createElement('img'),{src:partner.logo_url,alt:partner.name}))}
 else if(partner?.builtin_mark_key!=='nexcore')one('.v4-sponsor-wordmark svg').remove()
 text('.v4-sponsor-bottom>p',partner?.introduction||partner?.description||partner?.support_description||'')
 html('.v4-sponsor-bottom>div',`<span><b>${d.support_totals.equipment}</b> 件获奖外设</span><span><b>${d.support_totals.commemorative}</b> 枚参赛徽章</span>`)
 html('.official-partners',(d.official_partners??[]).map(x=>`<div>${x.logo_url?`<img src="${e(x.logo_url)}" alt="${e(x.name)}">`:''}<b>${e(x.english_name||x.name)}<span>${e(x.name)}</span></b><small>${e(x.category)}</small></div>`).join(''))
 return root.innerHTML
}
