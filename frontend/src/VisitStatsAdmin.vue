<script setup lang="ts">
import { onMounted, onUnmounted, ref, watchEffect } from 'vue'
import { api } from './api'

type DailyStats = { date: string; uv: number | null; pv: number | null }
type VisitSummary = {
  tracking_started_on: string | null
  as_of: string
  online: number | null
  today: DailyStats | null
  total_pv: number | null
  daily: DailyStats[]
}

const emit = defineEmits<{ unauthorized: [] }>()
const days = ref<7 | 30>(7)
const snapshot = ref<VisitSummary | null>(null)
const unavailable = ref(false)
const chart = ref<HTMLCanvasElement>()
let requestVersion = 0
let timer: number | undefined

const shanghaiTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

function stopPolling() {
  requestVersion++
  window.clearTimeout(timer)
}

async function refresh() {
  stopPolling()
  if (document.hidden) return
  const version = requestVersion
  try {
    const result: VisitSummary = await api('/admin/visits/summary?days=' + days.value)
    if (version !== requestVersion) return
    snapshot.value = result
    unavailable.value = false
  } catch (error) {
    if (version !== requestVersion) return
    if ((error as { status?: number }).status === 401) {
      emit('unauthorized')
      return
    }
    unavailable.value = true
  }
  if (version === requestVersion) timer = window.setTimeout(() => void refresh(), 10_000)
}

function selectRange(range: 7 | 30) {
  if (days.value === range) return
  days.value = range
  snapshot.value = null
  unavailable.value = false
  void refresh()
}

onMounted(() => {
  document.addEventListener('visibilitychange', refresh)
  void refresh()
})
onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', refresh)
})

watchEffect(() => {
  const canvas = chart.value
  const context = canvas?.getContext('2d')
  const daily = snapshot.value?.daily
  if (!canvas || !context || !daily?.length) return
  const left = 60, right = canvas.width - 33
  const top = 20, bottom = canvas.height - 42
  const max = Math.max(1, ...daily.map(day => Math.max(day.uv ?? 0, day.pv ?? 0)))
  const x = (index: number) => left + (right - left) * index / (daily.length - 1)
  const y = (value: number) => bottom - (bottom - top) * value / max

  context.clearRect(0, 0, canvas.width, canvas.height)
  context.font = '21px sans-serif'
  context.fillStyle = '#606266'
  context.strokeStyle = '#dcdfe6'
  context.lineWidth = 2
  context.textAlign = 'right'
  for (const value of [0, max]) {
    context.fillText(String(value), left - 10, y(value) + 7)
    context.beginPath()
    context.moveTo(left, y(value))
    context.lineTo(right, y(value))
    context.stroke()
  }
  context.textAlign = 'center'
  for (const index of [0, Math.floor(daily.length / 2), daily.length - 1]) {
    context.fillText(daily[index]!.date.slice(5), x(index), bottom + 31)
  }

  for (const [key, color] of [['pv', '#ad5025'], ['uv', '#1668b2']] as const) {
    context.strokeStyle = color
    context.fillStyle = color
    context.lineWidth = key === 'uv' ? 3 : 5
    context.beginPath()
    let previous = false
    daily.forEach((day, index) => {
      const value = day[key]
      if (value === null) {
        previous = false
        return
      }
      if (previous) context.lineTo(x(index), y(value))
      else context.moveTo(x(index), y(value))
      previous = true
    })
    context.stroke()
    daily.forEach((day, index) => {
      const value = day[key]
      if (value === null) return
      context.beginPath()
      context.arc(x(index), y(value), key === 'uv' ? 3 : 5, 0, 2 * Math.PI)
      context.fill()
    })
  }
})
</script>

<template>
  <section aria-labelledby="visit-stats-title">
    <h1 id="visit-stats-title">访问统计</h1>
    <el-alert v-if="unavailable" type="error" :closable="false"
      :title="snapshot ? '统计暂不可用 · 下方为上次成功数据' : '统计暂不可用'" />
    <div class="visit-metrics">
      <el-card shadow="never">
        <div class="metric-label">实时在线</div>
        <strong data-testid="visit-online">{{ snapshot?.online ?? '—' }}</strong>
        <div class="metric-note">最近 60 秒活跃浏览器</div>
        <div v-if="snapshot?.tracking_started_on" class="metric-note">
          更新于 {{ shanghaiTime.format(new Date(snapshot.as_of)) }}（北京时间）
        </div>
      </el-card>
      <el-card shadow="never">
        <div class="metric-label">今日访客（UV）</div>
        <strong data-testid="visit-uv">{{ snapshot?.today?.uv ?? '—' }}</strong>
        <div class="metric-note">北京时间自然日</div>
      </el-card>
      <el-card shadow="never">
        <div class="metric-label">今日浏览量（PV）</div>
        <strong data-testid="visit-pv">{{ snapshot?.today?.pv ?? '—' }}</strong>
        <div class="metric-note">北京时间自然日</div>
      </el-card>
    </div>
    <el-empty v-if="snapshot && !snapshot.tracking_started_on" description="统计未启用" />
    <p v-else-if="!snapshot && !unavailable" role="status">正在加载统计…</p>
    <h2>访问趋势</h2>
    <div class="visit-range">
      <el-button :type="days === 7 ? 'primary' : 'default'" :aria-pressed="days === 7" @click="selectRange(7)">近 7 天</el-button>
      <el-button :type="days === 30 ? 'primary' : 'default'" :aria-pressed="days === 30" @click="selectRange(30)">近 30 天</el-button>
    </div>
    <template v-if="snapshot?.tracking_started_on">
      <p>所选区间总浏览量 <strong data-testid="visit-total-pv">{{ snapshot.total_pv }}</strong></p>
      <div class="visit-legend"><span>每日访客（UV）</span><span>每日浏览量（PV）</span></div>
      <canvas ref="chart" class="visit-chart" width="800" height="235" aria-hidden="true"></canvas>
      <el-table :data="snapshot.daily" aria-label="每日访问统计">
        <el-table-column prop="date" label="日期" min-width="114" />
        <el-table-column label="访客 UV" min-width="112">
          <template #default="{ row }">{{ row.uv ?? '未开始采集' }}</template>
        </el-table-column>
        <el-table-column label="浏览量 PV" min-width="112">
          <template #default="{ row }">{{ row.pv ?? '未开始采集' }}</template>
        </el-table-column>
      </el-table>
    </template>
  </section>
</template>

<style scoped>
.visit-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  gap: 12px;
  margin-block: 14px 22px;
}

.visit-metrics strong {
  display: block;
  margin-block: 6px;
  font-size: 28px;
  font-variant-numeric: tabular-nums;
}

.metric-label {
  font-weight: 600;
}

.metric-note {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.visit-range, .visit-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.visit-range :deep(.el-button) {
  margin-left: 0;
}

.visit-legend {
  gap: 18px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.visit-legend span::before {
  display: inline-block;
  width: 12px;
  height: 3px;
  margin-right: 6px;
  vertical-align: middle;
  background: #1668b2;
  content: '';
}

.visit-legend span + span::before {
  background: #ad5025;
}

.visit-chart {
  display: block;
  width: min(100%, 800px);
  height: auto;
  margin-block: 12px;
}
</style>
