<script setup lang="ts">
import {ref,computed,watch,onUnmounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {api} from './api'
import Home from './Home.vue'
import Bracket from './Bracket.vue'
import './baseline.css'
import './public.css'
const route=useRoute(),router=useRouter()
const competitions=ref<any[]>([]),c=ref<any>(null),data=ref<any>(null),home=ref<any>(null),stages=ref<any[]>([])
const loading=ref(false),error=ref(''),updated=ref('')
const base=computed(()=>c.value?'/competitions/'+c.value.slug:'/competitions')
const page=computed(()=>route.path==='/'?'home':route.path==='/competitions'?'competitions':route.path.startsWith('/matches/')?'match':route.path.startsWith('/announcements/')?'announcement':route.path.split('/')[3]||'home')
const title:Record<string,string>={competitions:'当前与历史赛事',schedule:'赛程与对阵',standings:'完整积分榜',teams:'战队档案',announcements:'赛事公告',live:'直播中心',rules:'赛事规则',match:'比赛详情',announcement:'赛事公告'}
const state:Record<string,string>={unscheduled:'待安排',scheduled:'待开始',ongoing:'进行中',completed:'已结束',postponed:'已延期',cancelled:'已取消'}
const nav=[['赛事首页',''],['赛程对阵','/schedule'],['战队档案','/teams'],['赛事公告','/announcements']]
const isHome=computed(()=>page.value==='home')
const teamId=computed(()=>route.path.split('/')[4])
function dt(value:string){return value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}):'待安排'}
async function load(){
 loading.value=true;error.value=''
 try{
  competitions.value=await api('/competitions')
  if(page.value==='competitions'){data.value=competitions.value;return}
  let key=route.path.startsWith('/competitions/')?route.path.split('/')[2]:competitions.value[0]?.slug
  if(page.value==='match'||page.value==='announcement'){
   data.value=await api('/'+(page.value==='match'?'matches':'announcements')+'/'+route.path.split('/')[2]);key=data.value.competition_id
  }
  if(!key){c.value=null;home.value=null;data.value=null;return}
  c.value=await api('/competitions/'+key)
  if(isHome.value)home.value=await api('/competitions/'+key+'/home')
  else if(page.value==='schedule'){
   stages.value=await api('/competitions/'+key+'/stages')
   const q=new URLSearchParams(route.query as Record<string,string>)
   data.value=await api('/competitions/'+key+'/matches?'+q)
  } else if(page.value==='standings'){
   stages.value=await api('/competitions/'+key+'/stages');data.value=[]
   for(const s of stages.value)data.value.push({stage:s,rows:await api('/stages/'+s.id+'/standings')})
  } else if(page.value==='teams')data.value=await api('/competitions/'+key+'/teams'+(teamId.value?'/'+teamId.value:''))
  else if(['announcements','live'].includes(page.value))data.value=await api('/competitions/'+key+'/'+page.value)
  updated.value=new Date().toLocaleTimeString('zh-CN')
 }catch(e:any){error.value=e.message}finally{loading.value=false}
}
watch(()=>route.fullPath,()=>{data.value=null;home.value=null;load()},{immediate:true})
const timer=setInterval(()=>{if(!document.hidden&&(isHome.value||page.value==='match'||page.value==='schedule'))load()},30000)
function visible(){if(!document.hidden)load()}
document.addEventListener('visibilitychange',visible)
onUnmounted(()=>{clearInterval(timer);document.removeEventListener('visibilitychange',visible)})
</script>
<template>
<div id="gduf-designs"><section data-variant="广金主场 · 观赛优先"><div class="g-site g-match">
<div class="g-university"><span>GDUF <b>广东金融学院</b></span><span>学生社团赛事 / CAMPUS CS2</span></div>
<header class="g-nav"><RouterLink class="g-brand" :to="c?base:'/'"><strong>广金主场<span>↗</span></strong><small>GDUF COUNTER-STRIKE 2</small></RouterLink><nav aria-label="主导航"><RouterLink v-for="n in nav" :to="c?base+n[1]:(n[1]?'/competitions':'/')" :class="{'g-active':(n[1]===''&&isHome)||page===n[1].slice(1)}">{{n[0]}}</RouterLink></nav><span class="g-season">{{c?.season||'GDUF CS2'}}</span></header>
<div v-if="error" class="notice" role="alert">{{error}} <button class="g-button" @click="load">重试</button><small v-if="updated">上次更新 {{updated}}</small></div>
<div v-if="loading&&!data&&!home&&!isHome" class="empty" aria-busy="true">正在加载赛事信息…</div>
<Home v-if="isHome" :home="home" :loading="loading" :failed="!!error" />
<main v-else class="detail">
 <h1>{{title[page]||'广金主场'}}</h1>
 <p v-if="!loading&&!c&&page!=='competitions'" class="empty">赛事尚未公布</p>
 <template v-if="page==='competitions'"><RouterLink v-for="item in competitions" class="list-row" :to="'/competitions/'+item.slug"><b>{{item.name}}</b><span>{{item.season}} · {{item.status==='archived'?'历史赛事':'查看赛事 ↗'}}</span></RouterLink><p v-if="!competitions.length" class="empty">赛事尚未公布</p></template>
 <template v-if="c&&page==='rules'"><h2>{{c.name}}</h2><p class="prose">{{c.rules}}</p><h2>地图池</h2><p>{{c.map_pool.join(' / ')}}</p><p>组织方：{{c.organizer}}</p></template>
 <template v-if="page==='teams'&&data"><template v-if="teamId"><h2>{{data.name}}</h2><p>{{data.description}}</p><div v-for="m in data.members" class="list-row"><span>{{m.nickname}}</span><span>{{m.role}}{{m.captain?' · 队长':''}}</span></div><h2>当届比赛记录</h2><RouterLink v-for="m in data.matches" class="list-row" :to="'/matches/'+m.id">{{m.code}} · {{state[m.status]}}</RouterLink></template><template v-else><RouterLink v-for="t in data" class="list-row" :to="base+'/teams/'+t.id"><img v-if="t.logo" :src="t.logo" width="48" height="48" alt="队标"><b>{{t.name}}</b><span>{{t.description}}</span></RouterLink><p v-if="!data.length" class="empty">参赛名单待公布</p></template></template>
 <template v-if="page==='schedule'"><div class="filters"><button class="g-button" @click="router.replace({query:{...route.query,view:'list'}})">按时间列表</button><button class="g-button" @click="router.replace({query:{...route.query,view:'bracket'}})">完整对阵图</button></div><Bracket v-if="route.query.view==='bracket'" :stage-id="String(route.query.stage||stages[0]?.id||'')"/><form class="filters" @submit.prevent=""><label>日期 <input type="date" :value="route.query.date" @change="router.replace({query:{...route.query,date:($event.target as HTMLInputElement).value}})"></label><label>阶段 <select :value="route.query.stage||''" @change="router.replace({query:{...route.query,stage:($event.target as HTMLSelectElement).value}})"><option value="">全部</option><option v-for="s in stages" :value="s.id">{{s.name}}</option></select></label><button class="g-button" @click="router.replace({query:{}})">清除筛选</button></form><div class="bracket"><RouterLink v-for="m in data||[]" class="list-row" :to="'/matches/'+m.id"><span>{{dt(m.scheduled_at)}}<br>{{m.code}} · 第{{m.round}}轮 · {{m.group}}</span><b>{{m.teams[0]?.name||m.source_a||'轮空晋级'}} <em>{{m.confirmed?m.result.wins_a+' : '+m.result.wins_b:'VS'}}</em> {{m.teams[1]?.name||m.source_b||'轮空晋级'}}</b><span>BO{{m.best_of}} · {{state[m.status]}}</span></RouterLink></div><p v-if="data&&!data.length" class="empty">当前筛选无比赛</p></template>
 <template v-if="page==='standings'"><section v-for="block in data||[]"><h2>{{block.stage.name}}</h2><div class="table-scroll"><table><thead><tr><th>组别 / 排名</th><th>队伍</th><th>胜 / 负</th><th>积分</th><th>地图差</th><th>回合差</th></tr></thead><tbody><tr v-for="r in block.rows"><td>{{r.group}} / {{r.rank}}{{r.unresolved?'（待裁定）':''}}</td><td>{{r.name}}</td><td>{{r.wins}} / {{r.losses}}</td><td>{{r.points}}</td><td>{{r.map_diff}}</td><td>{{r.round_diff}}</td></tr></tbody></table></div></section><p v-if="data&&!data.length" class="empty">积分待公布</p></template>
 <template v-if="page==='match'&&data"><div class="g-duel"><div class="g-team" v-for="(t,i) in data.teams"><span class="g-teammark">{{t?.name?.slice(0,2)||'?'}}</span><h3>{{t?.name||(i===0?data.source_a:data.source_b)||'轮空晋级'}}</h3></div></div><p class="match-score">{{data.confirmed?data.result.wins_a+' : '+data.result.wins_b:'等待录分'}}</p><p>{{state[data.status]}} · BO{{data.best_of}} · {{dt(data.scheduled_at)}}（北京时间）</p><p v-if="data.result.result_type&&data.result.result_type!=='normal'">{{data.result.result_type==='forfeit'?'弃权':'技术判负'}} · {{data.result.reason}}</p><div class="list-row" v-for="m in data.result.maps||[]"><span>{{m.map_name}}</span><strong>{{m.score_a}} : {{m.score_b}}</strong><span>{{m.overtime?'加时':''}}</span></div><h2>当场名单</h2><section v-for="t in data.teams"><h3>{{t?.name}}</h3><p v-for="m in t?.members||[]">{{m.nickname}} · {{m.role}}</p></section><RouterLink :to="base+'/live'" class="g-button">直播与回放 ↗</RouterLink></template>
 <template v-if="page==='announcements'"><RouterLink v-for="a in data||[]" class="list-row" :to="'/announcements/'+a.id"><b>{{a.pinned?'置顶 · ':''}}{{a.title}}</b><span>{{dt(a.publish_at)}}</span></RouterLink><p v-if="data&&!data.length" class="empty">暂无公告</p></template>
 <article v-if="page==='announcement'&&data"><h2>{{data.title}}</h2><time>{{dt(data.publish_at)}}</time><p class="prose">{{data.body}}</p></article>
 <template v-if="page==='live'"><section v-for="l in data||[]" class="live-block"><p>{{l.status==='live'?'管理员标记直播中':l.status==='replay'?'回放':'暂未开播'}}</p><a class="g-button" :href="l.room_url" target="_blank" rel="noopener">打开 B站直播间 ↗</a> <a v-if="l.replay_url" class="g-button" :href="l.replay_url" target="_blank" rel="noopener">观看回放 ↗</a><p>直播状态由管理员维护，第三方播放器不可用时请使用外链。</p></section><p v-if="data&&!data.length" class="empty">暂无直播配置</p></template>
</main>
<footer class="g-footer"><span><b>GDUF</b> 广东金融学院 · 学生社团赛事</span><span class="footer-links"><RouterLink v-if="c" :to="base+'/rules'">赛事规则</RouterLink><RouterLink v-if="c" :to="base+'/live'">直播中心</RouterLink><RouterLink to="/competitions">历史赛事</RouterLink><RouterLink to="/admin/login">管理</RouterLink></span></footer>
</div></section></div>
</template>
