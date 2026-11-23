<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from './api'

type Match = {
  id: string
  code: string
  label?: string
  bracket: string
  round: number
  status: string
  best_of: number
  teams: ({ name: string } | null)[]
  source_a: string
  source_b: string
  confirmed: boolean
  result: { wins_a: number; wins_b: number }
}

type Edge = { source: string; target: string; outcome: 'winner' | 'loser'; slot: string }
type Bracket = { matches: Match[]; edges?: Edge[]; bye_sources?: { name?: string; source: string }[] }

const props = defineProps<{ stageId: string; single?: boolean }>()
const graph = ref<Bracket | null>(null)
const error = ref('')
const selectedRound = ref('')

watch(() => props.stageId, async (id, _, onCleanup) => {
  let active = true
  onCleanup(() => { active = false })
  graph.value = null
  error.value = ''
  selectedRound.value = ''
  if (!id) return
  try {
    const response = await api('/stages/' + id + '/bracket')
    if (active) graph.value = response
  } catch (cause) {
    if (active) error.value = cause instanceof Error ? cause.message : String(cause)
  }
}, { immediate: true })

const bracket = computed(() => {
  const matches = graph.value?.matches ?? []
  const finalRound = props.single ? Math.max(0, ...matches.map(match => match.round)) : 0
  const knockoutLabels = ['决赛', '半决赛', '四分之一决赛']
  const rounds = new Map<string, Match[]>()
  const byId = new Map<string, { code: string; round: string }>()
  const outgoing = new Map<string, Edge[]>()

  for (const match of matches) {
    const knockout = match.bracket === 'upper' ? knockoutLabels[finalRound - match.round] : undefined
    const label = match.label || knockout || match.bracket + ' / 第' + match.round + '轮'
    if (!rounds.has(label)) rounds.set(label, [])
    rounds.get(label)!.push(match)
    byId.set(match.id, { code: match.code, round: label })
  }
  for (const edge of graph.value?.edges ?? []) {
    if (!byId.has(edge.target)) continue
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, [])
    outgoing.get(edge.source)!.push(edge)
  }
  return { rounds: [...rounds], byId, outgoing }
})

watch(() => bracket.value.rounds, rounds => {
  if (!rounds.some(([label]) => label === selectedRound.value)) selectedRound.value = rounds[0]?.[0] ?? ''
})

function source(value: string) {
  if (value?.startsWith('group:')) {
    const [, group, rank] = value.split(':')
    return group + '组第' + rank + '名'
  }
  return value?.replace(':winner', ' 胜者').replace(':loser', ' 败者') || '待定'
}
</script>

<template>
  <p v-if="error" role="alert">{{ error }}</p>
  <p v-else-if="!graph">正在加载对阵图…</p>
  <template v-else>
    <p v-if="graph.bye_sources?.length">轮空晋级（不计比赛胜利）：{{ graph.bye_sources.map(bye => bye.name || source(bye.source)).join('、') }}</p>
    <p v-if="!graph.matches.length">暂无已发布对阵</p>
    <template v-else>
      <label v-if="bracket.rounds.length > 1" class="bracket-round-picker">
        轮次
        <select v-model="selectedRound" aria-label="轮次">
          <option v-for="[round] in bracket.rounds" :key="round">{{ round }}</option>
        </select>
      </label>
      <div class="bracket-board" aria-label="晋级对阵" tabindex="0">
        <section v-for="[round, matches] in bracket.rounds" :key="round" :class="{ 'bracket-round--selected': round === selectedRound }">
          <h2>{{ round }}</h2>
          <RouterLink v-for="match in matches" :key="match.id" :to="'/matches/' + match.id" class="bracket-node">
            <small>{{ match.code }} · BO{{ match.best_of }}{{ match.status === 'cancelled' ? ' · 已取消' : '' }}</small>
            <p>{{ match.teams[0]?.name || source(match.source_a) }} <strong>{{ match.confirmed ? match.result.wins_a : '–' }}</strong></p>
            <p>{{ match.teams[1]?.name || source(match.source_b) }} <strong>{{ match.confirmed ? match.result.wins_b : '–' }}</strong></p>
            <span v-for="edge in bracket.outgoing.get(match.id)" :key="edge.target + edge.slot" class="bracket-next">
              {{ edge.outcome === 'winner' ? '胜者' : '败者' }} → {{ bracket.byId.get(edge.target)?.round }} · {{ bracket.byId.get(edge.target)?.code }}
            </span>
          </RouterLink>
        </section>
      </div>
    </template>
    <details v-if="graph.edges?.length">
      <summary>晋级来源关系</summary>
      <p v-for="edge in graph.edges" :key="edge.source + edge.target + edge.slot">
        {{ bracket.byId.get(edge.source)?.code }}（{{ edge.outcome === 'winner' ? '胜者' : '败者' }}） → {{ bracket.byId.get(edge.target)?.code }} · {{ edge.slot }}
      </p>
    </details>
  </template>
</template>

<style>
.public-site .bracket-board{display:flex;gap:24px;overflow-x:auto;padding-bottom:20px;align-items:stretch}
.public-site .bracket-board>section{flex:0 0 230px;display:flex;flex-direction:column;justify-content:space-around;gap:18px}
.public-site .bracket-board h2{font-size:13px;margin:0}
.public-site .bracket-node{padding:14px;background:var(--panel);border:1px solid var(--line);border-left:2px solid var(--accent)}
.public-site .bracket-node small{color:var(--muted);font-size:10px}
.public-site .bracket-node p{display:flex;justify-content:space-between;gap:12px;font-size:12px;overflow-wrap:anywhere}
.public-site .bracket-round-picker,.public-site .bracket-next{display:none}
@media (max-width:760px){
  .public-site .bracket-board{display:block;padding-bottom:8px}
  .public-site .bracket-board>section{display:none}
  .public-site .bracket-board>.bracket-round--selected{display:block;margin:12px 0}
  .public-site .bracket-node{display:block;margin:8px 0}
  .public-site .bracket-node small{font-size:12px}
  .public-site .bracket-round-picker{display:inline-flex;align-items:center;gap:6px;font-size:12px;max-width:100%}
  .public-site .event-body .bracket-round-picker select{margin:0;min-height:44px;min-width:0}
  .public-site .bracket-next{display:block;color:var(--accent);font-size:12px;margin-top:5px;overflow-wrap:anywhere}
}
</style>
