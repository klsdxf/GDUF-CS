<script setup lang="ts">
import {ref} from 'vue'
import {api} from './api'
const emit=defineEmits<{completed:[]}>()
const preview=ref<any>(null),batch=ref<any>(null),busy=ref(false),error=ref('')
async function run(fn:()=>Promise<void>){busy.value=true;error.value='';try{await fn()}catch(e:any){error.value=e.message}finally{busy.value=false}}
async function inspect(){await run(async()=>{batch.value=null;preview.value=await api('/admin/test-data-imports/preview','POST',{package_key:'public-test',package_version:'1'})})}
async function commit(){await run(async()=>{batch.value=await api('/admin/test-data-imports/'+preview.value.id+'/commit','POST',{content_sha256:preview.value.content_sha256},{'Idempotency-Key':preview.value.id});emit('completed')})}
</script>
<template>
<section><h1>测试数据初始化</h1><el-alert title="示例／测试数据：秋季赛保持进行中，独立测试排名冠军为 Poppin'Party。" type="warning" :closable="false"/>
<p>预览后提交：三届赛事目录、四支战队、20 名成员、现有赛程、三条公告、赞助与奖品及四队测试排名。相同数据包重复提交返回原批次，不覆盖后台修改。</p>
<el-alert v-if="error" :title="error" type="error" :closable="false"/>
<el-button :loading="busy" @click="inspect">预览测试数据</el-button>
<template v-if="preview"><p>数据包 public-test / v1 · {{preview.already_imported?'已导入，将返回原批次':'待提交'}} · 摘要 {{preview.content_sha256}}</p><p>数量：{{preview.counts}}</p>
<el-alert v-for="c in preview.conflicts" :key="c" :title="c" type="error" :closable="false"/>
<h2>公开内容调整</h2><div v-for="c in preview.content_changes" :key="c.field"><b>{{c.field}}</b><p>{{c.before}} → {{c.after}}</p><small>{{c.reason}}</small></div>
<h2>补充的合成测试对局</h2><p v-for="m in preview.supplemental_matches" :key="m.source_key">{{m.label}} · {{m.a}} / {{m.b}} · {{m.wins_a}}:{{m.wins_b}} · 未提供逐图成绩</p>
<el-button type="primary" :disabled="busy||!!preview.conflicts.length" @click="commit">{{preview.already_imported?'查看原导入批次':'确认提交测试数据'}}</el-button></template>
<el-alert v-if="batch" :title="'测试数据已保存，批次：'+batch.id" type="success" :closable="false"/>
</section>
</template>
