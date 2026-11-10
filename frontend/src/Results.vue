<script setup lang="ts">
import {ref,computed,watch,nextTick,onMounted,onUnmounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {api} from './api'
import {demoData,render,score,teamName,awards,type ResultDTO} from './results/render'
import {escape as e,updatePageMeta,liveUrl} from './redesign/presentation'
import './results/reference-v6.css'
import css from './results/reference-v6.css?raw'
import {offlineRuntime} from './results/offline'
const props=defineProps<{previewData?:ResultDTO}>()
const emit=defineEmits<{competition:[value:any]}>()
const route=useRoute(),router=useRouter(),root=ref<HTMLElement>(),dialog=ref<HTMLDialogElement>()
const data=ref<ResultDTO|null>(null),loading=ref(true),error=ref(''),missing=ref(false),selected=ref(0),query=ref(''),title=ref(''),body=ref('')
const demo=!props.previewData&&(import.meta.env.VITE_PUBLIC_DATA_MODE||'demo')==='demo'
const html=computed(()=>data.value?render(data.value,selected.value,demo):'')
let sequence=0,opener:HTMLElement|null=null,dispose=()=>{}
let syncSequence=0,unmounted=false
async function load(){const id=++sequence;loading.value=true;error.value='';missing.value=false;data.value=null
 try{if(props.previewData)data.value=props.previewData
 else if(demo){if(route.params.pathMatch&&route.path!=='/results'&&route.path!=='/results/autumn')throw Object.assign(new Error('结果不存在'),{status:404});data.value=demoData()}
 else {const slug=route.path.split('/')[2];const d=await api(slug?'/competitions/'+encodeURIComponent(slug)+'/results':'/results/latest');if(id!==sequence)return;data.value=d}
 emit('competition',data.value?.competition||null)
 updatePageMeta(route.path,false,'最终排名'+(data.value?' · '+data.value.competition.name:''))
 }catch(err:any){if(id!==sequence)return;missing.value=err.status===404;error.value=missing.value?'内容不存在或尚未公开':err.message;updatePageMeta(route.path,missing.value,missing.value?'':'服务暂不可用')}finally{if(id===sequence)loading.value=false}
}
watch(()=>route.fullPath,()=>{if(route.query.edition){router.replace('/results/'+encodeURIComponent(String(route.query.edition)));return}selected.value=0;query.value='';load()},{immediate:true})
watch(()=>props.previewData,load)
function filter(){const rows=root.value?.querySelectorAll<HTMLElement>('[data-team]');let n=0;rows?.forEach(r=>{r.hidden=!r.dataset.team!.toLowerCase().includes(query.value.trim().toLowerCase());if(!r.hidden)n++});const count=root.value?.querySelector('#team-count');if(count)count.textContent=query.value?`找到 ${n} 支队伍`:`${n} 支${demo?'示例':''}队伍`;const empty=root.value?.querySelector<HTMLElement>('#empty');if(empty)empty.hidden=n>0}
function animate(){dispose();dispose=()=>{};const el=root.value;if(!el)return;const hero=el.querySelector<HTMLElement>('.v4-champion'),scene=el.querySelector<HTMLElement>('.v5-seal-scene'),object=el.querySelector<HTMLElement>('.v5-seal-object');if(!hero||!scene||!object)return
 let frame=0;const fine=matchMedia('(hover:hover) and (pointer:fine)');const move=(ev:PointerEvent)=>{if(!fine.matches||document.hidden||frame)return;frame=requestAnimationFrame(()=>{const r=hero.getBoundingClientRect();hero.style.setProperty('--light-x',((ev.clientX-r.left)/r.width*100)+'%');hero.style.setProperty('--light-y',((ev.clientY-r.top)/r.height*100)+'%');const s=scene.getBoundingClientRect();object.style.setProperty('--seal-rx',(7-((ev.clientY-s.top)/s.height-.5)*12)+'deg');object.style.setProperty('--seal-ry',(-13+((ev.clientX-s.left)/s.width-.5)*18)+'deg');frame=0})};const leave=()=>{object.style.removeProperty('--seal-rx');object.style.removeProperty('--seal-ry')}
 hero.addEventListener('pointermove',move,{passive:true});scene.addEventListener('pointerleave',leave)
 const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('v5-reveal');observer.unobserve(entry.target)}}),{threshold:.12});el.querySelectorAll('.v4-runners article,.v4-road,.v4-section-head,.v4-equipment-grid,.v4-presenting').forEach(x=>observer.observe(x))
 dispose=()=>{cancelAnimationFrame(frame);observer.disconnect();hero.removeEventListener('pointermove',move);scene.removeEventListener('pointerleave',leave)}
}
async function syncResultDOM(){const ticket=++syncSequence;await nextTick();if(unmounted||ticket!==syncSequence||!root.value)return;const search=root.value.querySelector<HTMLInputElement>('#search');if(search)search.value=query.value;filter();animate()}
onMounted(syncResultDOM)
watch(html,syncResultDOM)
async function open(t:string,b:string,source?:HTMLElement){title.value=t;body.value=b;opener=source||document.activeElement as HTMLElement;await nextTick();dialog.value?.showModal()}
function close(){dialog.value?.close();opener?.focus()}
async function replay(){if(!data.value)return;const rows=demo?[]:await api('/competitions/'+encodeURIComponent(data.value.competition.slug)+'/live');await open('赛事回顾',rows.filter((r:any)=>liveUrl(r.replay_url)).map((r:any)=>`<p><a href="${e(liveUrl(r.replay_url))}" target="_blank" rel="noopener">观看回放 ↗</a></p>`).join('')||'<h2>精彩，留给回放。</h2><p>本届暂无已发布回放。</p>')}
function click(ev:MouseEvent){const b=(ev.target as HTMLElement).closest<HTMLElement>('button');if(!b||!data.value)return;const d=data.value
 if(b.dataset.award!==undefined){selected.value=Number(b.dataset.award);nextTick(()=>root.value?.querySelector<HTMLElement>('#award-tab-'+selected.value)?.focus())}
 if(b.dataset.match){const m=[d.final_match,...d.champion_path].find(m=>m.id===b.dataset.match);open(m.label||'决赛逐图赛果',`<h2>${e(teamName(d,m.a_team_id))} <span class="modal-score">${e(score(m))}</span> ${e(teamName(d,m.b_team_id))}</h2><p>BO${m.best_of}${demo?' · 赛后示例':''}</p>`+(m.maps||[]).map((x:any)=>`<div class="map-detail"><span>${e(x.map_name)}</span><b>${x.score_a} : ${x.score_b}</b></div>`).join('')+(!m.maps?.length?'<p>暂无逐图成绩</p>':'')+(!demo?`<p><a href="/matches/${e(m.id)}">打开比赛详情 ↗</a></p>`:''),b)}
 if(b.dataset.prize){const p=d.placements.find(p=>p.id===b.dataset.prize);open('奖品详情',`<h2>${e(p.team.name)}</h2>`+awards(d,p).map(({z,a})=>`<p>${e(z.name)} × ${a.quantity} ${e(z.unit)}<br>${e(z.description||'')}</p>`).join(''),b)}
 if(b.dataset.dialog==='partner'){const p=d.presenting_partner;open('合作支持详情',`<h2>${e(p.name)} ${e(p.english_name)}</h2><p>${e(p.introduction||p.description||p.support_description)}</p>`+(p.official_url?`<a href="${e(p.official_url)}" target="_blank" rel="noopener">品牌官网 ↗</a>`:''),b)}
}
function keys(ev:KeyboardEvent){const t=ev.target as HTMLElement;if(!t.matches('[data-award]'))return;const tabs=Array.from(root.value!.querySelectorAll<HTMLElement>('[data-award]'));let i=tabs.indexOf(t);if(ev.key==='Home')i=0;else if(ev.key==='End')i=tabs.length-1;else if(ev.key==='ArrowLeft')i=(i+tabs.length-1)%tabs.length;else if(ev.key==='ArrowRight')i=(i+1)%tabs.length;else return;ev.preventDefault();ev.stopPropagation();tabs[i]?.click()}
async function download(){if(!data.value)return;const d=data.value
 // Build solely from the public DTO, never clone the app, cookies or administration DOM.
 const variants=d.placements.filter(p=>p.rank_from<=3).map((_,i)=>render(d,i,demo));let styles=css
 styles+='\n'+await (await fetch('/redesign/assets/fonts.css')).text()
 const urls=[...new Set(Array.from(styles.matchAll(/url\(['"]?([^)'"\s]+)['"]?\)/g),m=>m[1]!))]
 const toData=async(url:string)=>{const blob=await(await fetch(url)).blob();return await new Promise<string>(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.readAsDataURL(blob)})}
 for(const u of urls)if(!u.startsWith('data:'))styles=styles.replaceAll(u,await toData(u.startsWith('/')?u:'/redesign/assets/'+u))
 for(let i=0;i<variants.length;i++)for(const u of [...new Set(Array.from(variants[i]!.matchAll(/(?:src|href)="(\/media\/[^\"]+)"/g),m=>m[1]!))])variants[i]=variants[i]!.replaceAll(u,await toData(u))
 const info:Record<string,{title:string;body:string}>={}
 for(const m of [d.final_match,...d.champion_path])info['match:'+m.id]={title:m.label||'决赛逐图赛果',body:`<h2>${e(teamName(d,m.a_team_id))} ${e(score(m))} ${e(teamName(d,m.b_team_id))}</h2>`+(m.maps||[]).map((x:any)=>`<div class="map-detail"><span>${e(x.map_name)}</span><b>${x.score_a} : ${x.score_b}</b></div>`).join('')}
 for(const p of d.placements)info['prize:'+p.id]={title:'奖品详情',body:`<h2>${e(p.team.name)}</h2>`+awards(d,p).map(({z,a})=>`<p>${e(z.name)} × ${a.quantity} ${e(z.unit)}<br>${e(z.description)}</p>`).join('')}
 info.partner={title:'合作支持详情',body:`<h2>${e(d.presenting_partner?.name)}</h2><p>${e(d.presenting_partner?.introduction||d.presenting_partner?.description||d.presenting_partner?.support_description)}</p>`}
 const encode=(v:any)=>JSON.stringify(v).replaceAll('<','\\u003c')
 const js='('+offlineRuntime.toString()+')('+encode(variants)+','+encode(info)+')'
 const shell=document.querySelector('.public-site.results-page')!
 const header=shell.querySelector('.header')?.outerHTML||'',footer=shell.querySelector('.footer')?.cloneNode(true) as HTMLElement|undefined
 footer?.querySelectorAll('button').forEach(el=>el.remove())
 const contents='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+e(d.competition.name)+' 最终排名</title><style>'+styles+'</style><body style="margin:0"><div class="public-site results-page v5-motion-on">'+header+'<main>'+variants[0]+'</main>'+(footer?.outerHTML||'')+'<dialog aria-labelledby="offline-dialog-title"><div class="dialog-top"><span id="offline-dialog-title" data-title></span><button data-close aria-label="关闭弹窗">×</button></div><div data-body></div></dialog></div><script>'+js+'<'+ '/script></body></html>'
 const url=URL.createObjectURL(new Blob([contents],{type:'text/html;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='GDUFCS-results-'+d.competition.slug+'.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
defineExpose({replay,download})
const timer=setInterval(()=>{if(!demo&&!props.previewData&&!document.hidden)load()},30000)
onUnmounted(()=>{unmounted=true;syncSequence++;sequence++;dispose();dispose=()=>{};clearInterval(timer)})
</script>
<template>
<div ref="root" @click="click" @keydown="keys" @input="query=($event.target as HTMLInputElement).value;filter()">
 <div v-if="loading" class="results-loading empty-state" role="status">正在加载最终排名…</div>
 <div v-else-if="error" class="empty-state" role="alert"><h1>{{missing?'页面不存在':'服务暂不可用'}}</h1><p>{{error}}</p><button v-if="!missing" class="btn" @click="load">重试</button></div>
 <div v-else-if="!data" class="empty-state"><h1>最终排名待公布</h1></div>
 <div v-else v-html="html"></div>
</div>
<dialog ref="dialog" id="result-dialog" aria-labelledby="result-dialog-title" @cancel.prevent="close" @close="opener?.focus()" @click="(ev:any)=>{if(ev.target===dialog){const r=dialog!.getBoundingClientRect();if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)close()}}"><div class="dialog-top"><span id="result-dialog-title">{{title}}</span><button aria-label="关闭弹窗" @click="close">×</button></div><div v-html="body"></div></dialog>
</template>
<style>
.public-site.results-page .results-loading{min-height:650px}.public-site.results-page .v4-road{overflow-x:auto}.public-site.results-page #product-visual{object-fit:contain;max-width:100%;max-height:380px}.public-site.results-page .v4-sponsor-wordmark img{max-height:120px;max-width:240px;object-fit:contain}.public-site.results-page .official-partners img{max-height:60px;max-width:100%;object-fit:contain}.public-site.results-page .v4-type h3{overflow-wrap:anywhere}.public-site.results-page .v4-runners{grid-auto-rows:auto}
</style>
