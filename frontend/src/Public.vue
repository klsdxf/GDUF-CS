<script setup lang="ts">
import {ref,computed,watch,nextTick,onUnmounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {renderDemo,demoDialog,demoAction} from './redesign/demo'
import {loadPublic,renderApi,teamDetail,article,liveBody,base} from './redesign/data'
import Bracket from './Bracket.vue'
import './redesign/reference.css'

const route=useRoute(),router=useRouter()
const mode=import.meta.env.VITE_PUBLIC_DATA_MODE||'demo'
if(!['demo','api'].includes(mode))throw new Error('VITE_PUBLIC_DATA_MODE 必须为 demo 或 api')
const previousBackground=document.body.style.backgroundColor
document.body.style.backgroundColor='#101216'
const demo=mode==='demo',revision=ref(0),season=ref('all'),map=ref(0)
const model=ref<any>({competitions:[],news:[]}),loading=ref(false),error=ref(''),dialog=ref<HTMLDialogElement>(),dialogTitle=ref(''),dialogBody=ref('')
const returnTo=ref(''),transient=ref(false)
let sequence=0,dialogSequence=0
const cbase=computed(()=>demo?'/competitions/'+(route.path.startsWith('/competitions/')?route.path.split('/')[2]:'autumn'):model.value.c?base(model.value.c):model.value.competitions[0]?base(model.value.competitions[0]):'/competitions')
const displayRoute=computed(()=>demo&&modalRoute.value&&returnTo.value?router.resolve(returnTo.value):route)
const active=computed(()=>displayRoute.value.path==='/'?'home':displayRoute.value.path.includes('/schedule')?'schedule':displayRoute.value.path.includes('/teams')?'teams':displayRoute.value.path.startsWith('/announcements')?'news':'events')
const modalRoute=computed(()=>route.path.startsWith('/announcements/')||!!route.path.match(/^\/competitions\/[^/]+\/(teams\/[^/]+|live)$/))
const html=computed(()=>{revision.value;return demo?renderDemo(displayRoute.value.path,displayRoute.value.query):renderApi(model.value,route.path,route.query,season.value,map.value)})
const bracketStages=computed(()=>model.value.stages?.filter((s:any)=>!route.query.stage||s.id===route.query.stage)||[])
function defaultReturn(){return route.path.startsWith('/announcements/')?'/announcements':route.path.replace(/\/teams\/[^/]+$/,'/teams').replace(/\/live$/,'')}
async function open(title:string,body:string){dialogTitle.value=title;dialogBody.value=body;await nextTick();if(!dialog.value?.open)dialog.value?.showModal()}
async function syncDialog(){
 const ticket=++dialogSequence
 if(!modalRoute.value){dialog.value?.close();return}
 let result:any=null
 if(demo){if(route.path.startsWith('/announcements/'))result=demoDialog('news',route.path.split('/')[2]);else if(route.path.includes('/teams/'))result=demoDialog('team',route.path.split('/')[4]);else result=demoDialog('live','')}
 else if(model.value.detail&&route.path.startsWith('/announcements/'))result={title:'赛事公告',body:article(model.value.detail)}
 else if(model.value.detail&&route.path.includes('/teams/'))result={title:'当届战队',body:teamDetail(model.value.detail)}
 else if(route.path.endsWith('/live'))result={title:'直播与回放',body:liveBody(model.value.live||[])}
 if(ticket!==dialogSequence)return
 if(result)await open(result.title,result.body)
 else await open('内容不存在','<p>该示例或内容不存在。</p>')
}
async function load(){const ticket=++sequence;error.value='';if(demo){await syncDialog();return}loading.value=true;model.value={competitions:[],news:[]};try{const result=await loadPublic(route.path);if(ticket===sequence){model.value=result;await syncDialog()}}catch(err:any){if(ticket===sequence)error.value=err.message}finally{if(ticket===sequence)loading.value=false}}
watch(()=>route.path,(_path,oldPath)=>{map.value=0;transient.value=false;dialog.value?.close();load();if(!modalRoute.value&&!oldPath?.match(/^(\/announcements\/|\/competitions\/[^/]+\/(teams\/[^/]+|live)$)/))window.scrollTo({top:0});document.title=(route.path==='/'?'首页':route.path.startsWith('/matches/')?'比赛详情':route.path.startsWith('/announcements')?'赛事公告':'赛事')+' · GDUF CS'},{immediate:true})
function close(){dialog.value?.close();dialogSequence++;if(modalRoute.value){const to=returnTo.value||defaultReturn();returnTo.value='';router.push(to)}else transient.value=false}
async function live(){if(cbase.value==='/competitions'){transient.value=true;await open('直播与回放',liveBody([]));return}returnTo.value=route.fullPath;router.push(cbase.value+'/live')}
function updateQuery(key:string,value:string){const q={...route.query};if(value)q[key]=value;else delete q[key];router.replace({query:q})}
async function click(event:MouseEvent){
 const target=event.target as HTMLElement,anchor=target.closest('a'),button=target.closest('button')
 if(target.closest('[data-close]')){event.preventDefault();close();if(anchor)router.push(anchor.getAttribute('href')!);return}
 if(anchor){const href=anchor.getAttribute('href');if(href?.startsWith('/')&&!href.startsWith('//')&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&event.button===0&&anchor.target!=='_blank'){event.preventDefault();if(href.includes('/teams/')||href.startsWith('/announcements/'))returnTo.value=route.fullPath;router.push(href)}return}
 if(!button)return;const d=button.dataset
 if(d.season!==undefined){season.value=d.season;demoAction('season',d.season);revision.value++}
 if(d.day!==undefined){demoAction('day',d.day);revision.value++}
 if(d.date!==undefined)updateQuery('date',d.date)
 if(d.view!==undefined)updateQuery('view',d.view)
 if(d.map!==undefined){map.value=Number(d.map);demoAction('map',d.map);revision.value++;await nextTick();document.getElementById('map-tab-'+d.map)?.focus()}
 if(d.news!==undefined){returnTo.value=route.fullPath;router.push('/announcements/'+d.news)}
 if(d.team!==undefined){returnTo.value=route.fullPath;router.push(cbase.value+'/teams/'+d.team)}
 if(d.action==='live')await live()
 if(d.action==='credits'){transient.value=true;await open('预览与素材说明',`<h2>关于这份预览</h2><p>${demo?'赛事、队名、昵称、日期和比分均为设计演示，公开前台不连接业务 API。':'公开内容通过现有 API 读取，以管理员发布结果为准。'}</p><p>游戏截图来自 Valve 的 <a href="https://store.steampowered.com/app/730/CounterStrike_2/" target="_blank" rel="noopener">Counter-Strike 2 官方商店页面</a>，地图配图为版式占位，不保证对应地图实景。</p><p>展示字体已保存在本地；中文使用系统字体。</p>`)}
}
function keys(event:KeyboardEvent){const t=event.target as HTMLElement;if(t.matches('[role=tab]')&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();const tabs=Array.from(document.querySelectorAll<HTMLElement>('.public-site [role=tab]')),i=tabs.indexOf(t);tabs[(i+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length]?.click()}}
function backdrop(event:MouseEvent){if(event.target!==dialog.value)return;const rect=dialog.value!.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)close()}
async function refresh(){if(document.hidden||demo||loading.value||modalRoute.value)return;const ticket=sequence;try{const result=await loadPublic(route.path);if(ticket===sequence)model.value=result}catch(err:any){error.value=err.message}}
const timer=setInterval(refresh,30000)
document.addEventListener('visibilitychange',refresh)
onUnmounted(()=>{document.body.style.backgroundColor=previousBackground;sequence++;dialogSequence++;clearInterval(timer);document.removeEventListener('visibilitychange',refresh)})
</script>
<template>
<div class="public-site" data-theme="blue" @click="click" @keydown="keys" @change="($event.target as HTMLElement).matches('[data-stage]')&&updateQuery('stage',($event.target as HTMLSelectElement).value)">
 <header class="header"><a class="brand" href="/" aria-label="GDUF CS 首页"><span class="brand-symbol">G<span>/</span></span><span>GDUF<span class="brand-cs">CS</span><small class="brand-spacer" aria-hidden="true">&nbsp;</small></span></a><nav class="main-nav" aria-label="主导航"><a v-for="n in [['home','首页','/'],['events','赛事','/competitions'],['schedule','赛程',cbase+'/schedule'],['teams','战队',cbase+'/teams'],['news','公告','/announcements']]" :key="n[0]" :href="n[2]" :class="{active:active===n[0]}" :aria-current="active===n[0]?'page':undefined">{{n[1]}}</a></nav><button class="watch" data-action="live"><span class="play-small">▷</span> 观看直播 <span>↗</span></button></header>
 <div v-if="error" class="empty-state" role="alert">{{error}} <button class="btn" @click="load">重试</button></div>
 <main :aria-busy="loading"><div v-if="loading" class="empty-state">正在加载赛事信息…</div><div v-else v-html="html"></div><Teleport defer to="#public-bracket" v-if="!demo&&!loading&&!error&&route.path.endsWith('/schedule')&&route.query.view==='bracket'"><div><p v-if="!bracketStages.length" class="empty-state">暂无已发布阶段</p><section v-for="stage in bracketStages" :key="stage.id"><h2>{{stage.name}}</h2><Bracket :stage-id="stage.id" /></section></div></Teleport></main>
 <footer class="footer"><div><a class="footer-brand" href="/">GDUF CS<span> / </span></a><p aria-hidden="true">&nbsp;</p></div><div class="footer-links"><a href="/competitions">全部赛事</a><a :href="cbase+'/rules'">赛事规则</a><button data-action="credits">素材说明</button><a href="/admin/login">管理</a></div><div class="footer-note">{{demo?'前端概念预览 · 示例数据':'赛事公开信息 · 真实数据'}}<br>{{demo?'不连接项目接口，不代表真实赛事安排':'以管理员正式发布信息为准'}}</div></footer>
 <dialog ref="dialog" id="dialog" aria-labelledby="dialog-label" @cancel.prevent="close" @click="backdrop"><div class="dialog-top"><span id="dialog-label">{{dialogTitle}}</span><button id="close-dialog" aria-label="关闭弹窗" @click="close">×</button></div><div id="dialog-body" v-html="dialogBody"></div></dialog>
</div>
</template>
<style>
body{margin:0}.public-site{min-height:100vh}.public-site .prose{white-space:pre-wrap;overflow-wrap:anywhere}.public-site .table-scroll{overflow-x:auto}.public-site .plain{background:transparent;color:inherit}.public-site .team-badge[src]{object-fit:contain;clip-path:none;background:transparent}.public-site .rules-body select{background:var(--panel);color:inherit}.public-site .event-body select{margin:0 0 20px 10px;background:var(--panel);color:inherit;padding:8px;max-width:100%}.public-site #dialog-body .fixture{color:#f8f9fb;display:block}.public-site #dialog-body .fixture-duel{display:flex;flex-wrap:wrap}.public-site .news-row h3,.public-site .team-name{overflow-wrap:anywhere}
</style>
