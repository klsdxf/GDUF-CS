<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from './api'

type Connection = { path: string; outcome: Edge['outcome'] }

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
const tree = ref<HTMLElement | null>(null)
const connections = ref<Connection[]>([])
const hasLoserEdges = computed(() => graph.value?.edges?.some(edge => edge.outcome === 'loser') ?? false)

watch(() => props.stageId, async (id, _, onCleanup) => {
  let active = true
  onCleanup(() => { active = false })
  graph.value = null
  error.value = ''
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

  for (const match of matches) {
    const knockout = match.bracket === 'upper' ? knockoutLabels[finalRound - match.round] : undefined
    const label = match.label || knockout || match.bracket + ' / 第' + match.round + '轮'
    if (!rounds.has(label)) rounds.set(label, [])
    rounds.get(label)!.push(match)
    byId.set(match.id, { code: match.code, round: label })
  }
  return { rounds: [...rounds], byId }
})

watch([tree, graph], ([surface, data], _, onCleanup) => {
  connections.value = []
  const edges = data?.edges ?? []
  if (!surface || !edges.length) return
  const board = surface
  const nodes = new Map(Array.from(surface.querySelectorAll<HTMLElement>('[data-bracket-match]'),
    node => [node.dataset.bracketMatch, node] as const))
  let frame = 0

  function measure() {
    frame = 0
    const bounds = board.getBoundingClientRect()
    const boxes = new Map([...nodes].map(([id, node]) => [id, node.getBoundingClientRect()]))
    let routed = 0
    connections.value = edges.flatMap(edge => {
      const from = boxes.get(edge.source)
      const to = boxes.get(edge.target)
      if (!from || !to || to.left <= from.right) return []

      const startX = from.right - bounds.left
      const startY = from.top + from.height / 2 - bounds.top
      const endX = to.left - bounds.left
      const endY = to.top + to.height * (edge.slot === 'b' ? .62 : .38) - bounds.top
      const half = (startX + endX) / 2
      // Route edges that skip a column around the cards in between.
      const rail = bounds.height - 6 - (routed % 3) * 5
      const path = endX - startX < 50
        ? `M ${startX} ${startY} H ${half} V ${endY} H ${endX}`
        : `M ${startX} ${startY} H ${startX + 8} V ${rail} H ${endX - 8} V ${endY} H ${endX}`
      if (endX - startX >= 50) routed++
      return [{ path, outcome: edge.outcome }]
    })
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(measure)
  }

  const observer = new ResizeObserver(schedule)
  observer.observe(surface)
  nodes.forEach(node => observer.observe(node))
  schedule()
  onCleanup(() => {
    observer.disconnect()
    cancelAnimationFrame(frame)
  })
}, { flush: 'post' })

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
      <p v-if="bracket.rounds.length > 1" class="bracket-scroll-hint" :class="{ 'bracket-has-legend': hasLoserEdges }">
        <span class="bracket-touch-hint">左右滑动查看各轮 →</span>
        <span v-if="hasLoserEdges">实线胜者 · 虚线败者</span>
      </p>
      <div class="bracket-board" role="region" aria-label="晋级对阵，可横向滚动" tabindex="0">
        <div ref="tree" class="bracket-tree">
          <svg v-if="connections.length" class="bracket-connections" aria-hidden="true">
            <path v-for="(connection, i) in connections" :key="i" :d="connection.path"
              :class="{ 'bracket-loser-edge': connection.outcome === 'loser' }" />
          </svg>
          <section v-for="[round, matches] in bracket.rounds" :key="round" class="bracket-round">
            <h2>{{ round }}</h2>
            <div class="bracket-round-matches">
              <RouterLink v-for="match in matches" :key="match.id" :to="'/matches/' + match.id"
                class="bracket-node" :data-bracket-match="match.id">
                <small class="bracket-match-meta">{{ match.code }} · BO{{ match.best_of }}{{ match.status === 'cancelled' ? ' · 已取消' : '' }}</small>
                <p><span>{{ match.teams[0]?.name || source(match.source_a) }}</span> <strong>{{ match.confirmed ? match.result.wins_a : '–' }}</strong></p>
                <p><span>{{ match.teams[1]?.name || source(match.source_b) }}</span> <strong>{{ match.confirmed ? match.result.wins_b : '–' }}</strong></p>
              </RouterLink>
            </div>
          </section>
        </div>
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
.public-site .bracket-board {
  max-width: 100%;
  overflow-x: auto;
  padding-bottom: 6px;
  overscroll-behavior-inline: contain;
  scrollbar-color: var(--accent) var(--panel);
  scrollbar-width: thin;
}
.public-site .bracket-tree {
  position: relative;
  display: flex;
  align-items: stretch;
  width: max-content;
  gap: 24px;
  padding-bottom: 23px;
}
.public-site .bracket-round {
  display: flex;
  flex: 0 0 230px;
  flex-direction: column;
  gap: 9px;
  min-width: 0;
  width: 230px;
}
.public-site .bracket-round h2 { min-height: 24px; margin: 0; font-size: 15px; line-height: 1.4; }
.public-site .bracket-round-matches {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: space-around;
  gap: 12px;
}
.public-site .bracket-node {
  position: relative;
  min-width: 0;
  border: 1px solid var(--line);
  border-left: 2px solid var(--accent);
  border-radius: 5px;
  padding: 12px 14px;
  background: var(--panel);
}
.public-site .bracket-node small { color: var(--muted); font-size: 10px; }
.public-site .bracket-node p {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 2.4ch;
  gap: 5px;
  align-items: baseline;
  font-size: 14px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.public-site .bracket-node p + p { margin-top: 3px; }
.public-site .bracket-node strong { font-size: 17px; text-align: end; }
.public-site .bracket-match-meta { display: block; margin-bottom: 4px; }
.public-site .bracket-connections {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.public-site .bracket-connections path { fill: none; stroke: var(--accent); stroke-width: 1.5; opacity: .75; }
.public-site .bracket-connections .bracket-loser-edge { stroke: var(--muted); stroke-dasharray: 3 3; }
.public-site .bracket-filters:empty,
.public-site .bracket-scroll-hint,
.public-site .bracket-touch-hint { display: none; }
.public-site .bracket-scroll-hint {
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 2px 10px;
  margin: 7px 0 10px;
  color: var(--muted);
  font-size: 12px;
}
.public-site .bracket-scroll-hint.bracket-has-legend { display: flex; }

@media (max-width: 760px) {
  .public-site .bracket-scroll-hint { display: flex; }
  .public-site .bracket-touch-hint { display: inline; }
  .public-site .bracket-round {
    flex-basis: clamp(126px, 39vw, 184px);
    width: clamp(126px, 39vw, 184px);
  }
  .public-site .bracket-round h2 { font-size: 13px; }
  .public-site .bracket-node { padding: 8px 9px; }
  .public-site .bracket-node p { font-size: 13px; }
  .public-site .bracket-node strong { font-size: 15px; }
}
</style>
