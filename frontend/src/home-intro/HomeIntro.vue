<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { HOME_POSTER } from './entry'
import { mountHomeIntro } from './motion'
import emblem from './assets/school-emblem.webp'
import player from './assets/player.webp'
import './home-intro.css'

const props = defineProps<{ getSurface: () => HTMLElement | null }>()
const emit = defineEmits<{ done: [restoreFocus: boolean] }>()
const opening = ref<HTMLElement | null>(null)
let stop: (() => void) | undefined

onMounted(() => {
  const surface = props.getSurface()
  if (!opening.value || !surface) {
    emit('done', false)
    return
  }
  stop = mountHomeIntro(opening.value, surface, restoreFocus => emit('done', restoreFocus))
})
onBeforeUnmount(() => stop?.())

function skipIntro() {
  emit('done', true)
}
</script>

<template>
  <Teleport to="body">
    <div id="gduf-home-intro" ref="opening" class="gduf-home-intro" role="region" aria-label="GDUFCS 开场" data-playing>
      <div class="handoff-veil" aria-hidden="true"></div>
      <div id="gdufcs-banner-preview">
        <section id="gduf-banner-stage" class="gduf-stage" aria-label="GDUFCS 开场动画" data-mode="playing">
          <div class="gduf-frame" aria-hidden="true"></div>
          <div class="gduf-scenery" aria-hidden="true">
            <img :src="HOME_POSTER" width="1440" height="810" alt="" fetchpriority="high" @error="emit('done', false)">
            <div class="handoff-home-mask"></div>
            <svg class="gduf-inset-edge" viewBox="0 0 1600 900" preserveAspectRatio="none" aria-hidden="true">
              <path d="M176 900 800 297 1424 900" fill="none" stroke="#ffcfab" stroke-opacity=".62" stroke-width="2" vector-effect="non-scaling-stroke"/>
            </svg>
          </div>

          <svg class="gduf-rays" viewBox="0 0 1600 900" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="gduf-ray-glow" x1="0" y1="0" x2="0" y2="1">
                <stop stop-color="#ffe5c9"/>
                <stop offset=".45" stop-color="#ff8465"/>
                <stop offset="1" stop-color="#ff8465" stop-opacity="0"/>
              </linearGradient>
            </defs>
            <path d="M 55 900 800 225 1545 900" fill="none" stroke="#f54d43" stroke-opacity=".17" stroke-width="12" vector-effect="non-scaling-stroke"/>
            <path d="M 55 900 800 225 1545 900" fill="none" stroke="url(#gduf-ray-glow)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
            <path d="M 16 900 800 225 1584 900" fill="none" stroke="url(#gduf-ray-glow)" stroke-opacity=".28" vector-effect="non-scaling-stroke"/>
          </svg>

          <div class="gduf-brand">
            <div class="gduf-wordmark">GDUFCS</div>
            <p data-copy="subtitle">GUANGDONG UNIVERSITY OF FINANCE CS2</p>
          </div>

          <div class="gduf-emblem">
            <svg class="gduf-orbit" viewBox="0 0 160 160" aria-hidden="true">
              <circle cx="80" cy="80" r="75" fill="none" stroke="currentColor" stroke-opacity=".17"/>
              <circle cx="80" cy="80" r="66" fill="none" stroke="currentColor" stroke-opacity=".48" stroke-dasharray="42 62 10 35 74 192" transform="rotate(-63 80 80)"/>
              <path d="M80 1v8m0 142v8M1 80h8m142 0h8" fill="none" stroke="currentColor" stroke-opacity=".58"/>
            </svg>
            <div class="gduf-seal">
              <div class="gduf-seal-art">
                <img :src="emblem" width="898" height="352" alt="广东金融学院校徽" @error="emit('done', false)">
                <span class="gduf-seal-placeholder">校徽</span>
              </div>
            </div>
          </div>

          <svg class="gduf-reticle" viewBox="0 0 64 64" fill="none" stroke="currentColor" aria-hidden="true">
            <path d="M23 7H7v16m34-16h16v16M7 41v16h16m18 0h16V41"/>
            <circle cx="32" cy="32" r="13"/>
            <path d="M32 13v12m0 14v12M13 32h12m14 0h12"/>
          </svg>

          <figure class="gduf-player">
            <img :src="player" alt="佩戴耳机的校园电竞选手" width="680" height="850" fetchpriority="high" @error="emit('done', false)">
            <figcaption data-copy="character">COUNTER-STRIKE 2</figcaption>
          </figure>

          <div class="gduf-message">
            <p class="gduf-category" data-copy="category">CAMPUS ESPORTS / CS2</p>
            <p class="gduf-slogan" data-copy="slogan">为热爱而战</p>
          </div>
        </section>

      </div><button type="button" class="handoff-skip" @click="skipIntro">跳过开场</button>
    </div>
  </Teleport>
</template>
