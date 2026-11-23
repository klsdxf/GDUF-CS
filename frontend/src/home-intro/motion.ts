const LAND_MS = 720
const RELEASE_MS = 180
const PHOTO_WAIT_MS = 500
const FAILSAFE_MS = 4700
const TRIANGLE = 'polygon(50% 33%, 50% 33%, 89% 100%, 11% 100%)'
const RECTANGLE = 'polygon(0 0, 100% 0, 100% 100%, 0 100%)'

const filterDefaults = { saturate: '1', sepia: '0', contrast: '1', brightness: '1' }

function photoFilter(filter: string) {
  return Object.entries(filterDefaults).map(([name, fallback]) => {
    const amount = filter.split(name + '(')[1]?.split(')', 1)[0] || fallback
    return name + '(' + amount + ')'
  }).join(' ')
}

function photoStyle(image: HTMLImageElement) {
  const style = getComputedStyle(image)
  return { filter: photoFilter(style.filter), objectPosition: style.objectPosition }
}

// Keep the approved 2.9s CSS entry clock and 900ms photo handoff on the same lifetime.
export function mountHomeIntro(opening: HTMLElement, surface: HTMLElement, done: (restoreFocus: boolean) => void) {
  const stage = opening.querySelector<HTMLElement>('.gduf-stage')
  const scene = stage?.querySelector<HTMLElement>('.gduf-scenery')
  const sceneImage = scene?.querySelector('img')
  const homeMask = scene?.querySelector<HTMLElement>('.handoff-home-mask')
  const veil = opening.querySelector<HTMLElement>('.handoff-veil')
  const skip = opening.querySelector<HTMLButtonElement>('.handoff-skip')
  if (!stage || !scene || !sceneImage || !homeMask || !veil || !skip || typeof scene.animate !== 'function') {
    done(false)
    return
  }

  const foreground = stage.querySelectorAll<HTMLElement>(
    '.gduf-frame, .gduf-rays, .gduf-brand, .gduf-player, .gduf-message, .gduf-reticle, .gduf-emblem, .gduf-inset-edge'
  )
  const tracks: Animation[] = []
  const events = new AbortController()
  const options = { signal: events.signal }
  const rootStyle = document.documentElement.style
  const previousOverflow = rootStyle.overflow
  const previousGutter = rootStyle.scrollbarGutter
  function lockScroll() {
    // Reserve only the gutter this browser uses in the unlocked homepage.
    // The API may have rendered a scrollable page since mount, so recheck before measuring.
    rootStyle.overflow = previousOverflow
    rootStyle.scrollbarGutter = previousGutter
    const unlockedWidth = document.documentElement.clientWidth
    rootStyle.overflow = 'hidden'
    if (document.documentElement.clientWidth !== unlockedWidth) rootStyle.scrollbarGutter = 'stable'
  }
  lockScroll()

  let stopped = false
  let landing = false
  let arrivalTimer: number | undefined
  let cleanupTimer: number | undefined

  function stop() {
    if (stopped) return
    stopped = true
    events.abort()
    window.clearTimeout(arrivalTimer)
    window.clearTimeout(cleanupTimer)
    tracks.forEach(track => track.cancel())
    delete surface.dataset.homeIntroLanding
    delete surface.dataset.homeIntroArrived
    rootStyle.overflow = previousOverflow
    rootStyle.scrollbarGutter = previousGutter
  }

  function finish(restoreFocus = document.activeElement === skip) {
    if (stopped) return
    stop()
    done(restoreFocus)
  }

  function animate(element: Element, keyframes: Keyframe[], timing: KeyframeAnimationOptions) {
    const track = element.animate(keyframes, { fill: 'both', ...timing })
    tracks.push(track)
    return track
  }

  function onComplete(track: Animation, completed: () => void) {
    void track.finished.then(() => { if (!stopped) completed() }, () => {})
  }

  function syncVisibility() {
    opening.toggleAttribute('data-suspended', document.hidden)
    stage!.dataset.suspended = String(document.hidden)
    for (const track of tracks) {
      if (document.hidden && track.playState === 'running') track.pause()
      else if (!document.hidden && track.playState === 'paused') track.play()
    }
    window.clearTimeout(cleanupTimer)
    if (!document.hidden) cleanupTimer = window.setTimeout(() => finish(), FAILSAFE_MS)
  }

  function beginLanding() {
    if (!stage || !scene || !sceneImage || !homeMask || !veil || !skip || stopped || landing) return
    landing = true
    const waitUntil = performance.now() + PHOTO_WAIT_MS
    const attempt = () => {
      if (stopped) return
      const target = surface.querySelector<HTMLImageElement>('.hero-photo')
      const hero = target?.closest<HTMLElement>('.hero')
      if (!target?.complete || !target.naturalWidth || !sceneImage.naturalWidth || !hero || sceneImage.currentSrc !== target.currentSrc) {
        if (performance.now() < waitUntil) {
          arrivalTimer = window.setTimeout(attempt, 50)
        } else {
          onComplete(animate(opening, [{ opacity: 1 }, { opacity: 0 }], {
            duration: 260, easing: 'ease-out'
          }), () => finish())
        }
        return
      }

      lockScroll()
      const start = scene.getBoundingClientRect()
      const end = target.getBoundingClientRect()
      const frame = stage.getBoundingClientRect()
      const heroBox = hero.getBoundingClientRect()
      const box = (rect: DOMRect) => ({
        left: (rect.left - frame.left) + 'px',
        top: (rect.top - frame.top) + 'px',
        width: rect.width + 'px',
        height: rect.height + 'px'
      })
      const fromPhoto = photoStyle(sceneImage)
      const toPhoto = photoStyle(target)

      homeMask.style.left = (heroBox.left - end.left) + 'px'
      homeMask.style.width = heroBox.width + 'px'
      homeMask.style.backgroundImage = getComputedStyle(hero, '::after').backgroundImage
      homeMask.style.backgroundSize = heroBox.width + 'px ' + heroBox.height + 'px'

      stage.dataset.landing = ''
      surface.dataset.homeIntroLanding = ''
      for (const layer of [...Array.from(foreground), skip]) {
        animate(layer, [{opacity: getComputedStyle(layer).opacity}, {opacity: 0}], {
          duration: 240, easing: 'ease-out'
        })
      }
      animate(veil, [{opacity: 1}, {opacity: 0}], { delay: 240, duration: 460, easing: 'ease-in-out' })
      animate(homeMask, [{opacity: 0}, {opacity: 1}], { delay: 150, duration: 570, easing: 'ease-in-out' })

      const motion = { duration: LAND_MS, easing: 'cubic-bezier(.36,.15,.28,1)' }
      const travel = animate(scene, [
        { ...box(start), clipPath: TRIANGLE, '--gduf-photo-floor-alpha': '0' },
        { ...box(end), clipPath: RECTANGLE, '--gduf-photo-floor-alpha': '1' }
      ], motion)
      animate(sceneImage, [fromPhoto, toPhoto], motion)

      onComplete(travel, () => {
        delete surface.dataset.homeIntroLanding
        surface.dataset.homeIntroArrived = ''
        onComplete(animate(scene, [{opacity: 1}, {opacity: 0}], {
          duration: RELEASE_MS, easing: 'ease-out'
        }), () => finish())
      })
      if (document.hidden) syncVisibility()
    }
    attempt()
  }

  opening.addEventListener('animationend', event => {
    if (event.target === opening && event.animationName === 'gduf-intro-clock') beginLanding()
  }, options)
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault()
      finish(true)
    }
  }, options)
  document.addEventListener('visibilitychange', syncVisibility, options)
  window.addEventListener('resize', () => {
    if (stage.hasAttribute('data-landing')) finish()
  }, options)
  syncVisibility()
  return stop
}
