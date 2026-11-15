<script setup lang="ts">
import {ref,watch,computed} from 'vue'
import {api} from './api'
const props=defineProps<{stageId:string}>()
const graph=ref<any>(null),error=ref('')
watch(()=>props.stageId,async(id)=>{graph.value=null;error.value='';if(id)try{graph.value=await api('/stages/'+id+'/bracket')}catch(e:any){error.value=e.message}},{immediate:true})
const rounds=computed(()=>{const groups:Record<string,any[]>={};for(const m of graph.value?.matches||[])(groups[m.bracket+' / 第'+m.round+'轮']??=[]).push(m);return groups})
function source(value:string){if(value.startsWith('group:')){const[,g,r]=value.split(':');return g+'组第'+r+'名'}return value.replace(':winner',' 胜者').replace(':loser',' 败者')||'待定'}
</script>
<template><p v-if="error" role="alert">{{error}}</p><p v-else-if="!graph">正在加载对阵图…</p><template v-else><p v-if="graph.bye_sources?.length">轮空晋级（不计比赛胜利）：{{graph.bye_sources.map((b:any)=>b.name||source(b.source)).join('、')}}</p><div class="bracket-board" aria-label="完整对阵图，可横向滚动" tabindex="0"><section v-for="(matches,round) in rounds"><h2>{{round}}</h2><RouterLink v-for="m in matches" :to="'/matches/'+m.id" class="bracket-node"><small>{{m.code}} · BO{{m.best_of}}{{m.status==='cancelled'?' · 已取消':''}}</small><p>{{m.teams[0]?.name||source(m.source_a)}} <strong>{{m.confirmed?m.result.wins_a:'–'}}</strong></p><p>{{m.teams[1]?.name||source(m.source_b)}} <strong>{{m.confirmed?m.result.wins_b:'–'}}</strong></p></RouterLink></section></div></template></template>
<style>
#gduf-designs .bracket-board{display:flex;gap:24px;overflow-x:auto;padding-bottom:20px;align-items:stretch}#gduf-designs .bracket-board>section{flex:0 0 230px;display:flex;flex-direction:column;justify-content:space-around;gap:18px}#gduf-designs .bracket-board h2{font-size:13px;margin:0}#gduf-designs .bracket-node{padding:14px;background:var(--g-panel);border:1px solid var(--g-rule);border-left:2px solid var(--g-red)}#gduf-designs .bracket-node small{color:var(--g-muted);font-size:10px}#gduf-designs .bracket-node p{display:flex;justify-content:space-between;gap:12px;font-size:12px}@media(max-width:540px){#gduf-designs .bracket-board{display:block}#gduf-designs .bracket-board>section{display:block;margin:20px 0}#gduf-designs .bracket-node{display:block;margin:12px 0}}
</style>
