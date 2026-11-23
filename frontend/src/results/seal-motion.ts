export function bindSealMotion(hero: HTMLElement, scene: HTMLElement, seal: HTMLElement) {
  const mouseHover = matchMedia('(hover: hover) and (pointer: fine)')
  const events = new AbortController()
  const options = { signal: events.signal, passive: true }
  let frame = 0
  let next: (() => void) | undefined
  let drag: { id: number; x: number; y: number; active: boolean } | undefined

  function queue(update: () => void) {
    next = update
    if (frame) return
    frame = requestAnimationFrame(() => {
      frame = 0
      next?.()
      next = undefined
    })
  }

  function rotate(x: number, y: number) {
    seal.style.setProperty('--seal-rx', x + 'deg')
    seal.style.setProperty('--seal-ry', y + 'deg')
  }

  function resetRotation() {
    cancelAnimationFrame(frame)
    frame = 0
    next = undefined
    seal.style.removeProperty('--seal-rx')
    seal.style.removeProperty('--seal-ry')
  }

  function hover(event: PointerEvent) {
    if (event.pointerType === 'touch' || drag || !mouseHover.matches || document.hidden) return
    queue(() => {
      const bounds = hero.getBoundingClientRect()
      const stage = scene.getBoundingClientRect()
      hero.style.setProperty('--light-x', (event.clientX - bounds.left) / bounds.width * 100 + '%')
      hero.style.setProperty('--light-y', (event.clientY - bounds.top) / bounds.height * 100 + '%')
      rotate(7 - ((event.clientY - stage.top) / stage.height - .5) * 12,
        -13 + ((event.clientX - stage.left) / stage.width - .5) * 18)
    })
  }

  function start(event: PointerEvent) {
    if (event.pointerType !== 'touch' || !event.isPrimary || drag) return
    resetRotation()
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, active: false }
  }

  function move(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.id) return
    const x = event.clientX - drag.x
    const y = event.clientY - drag.y
    if (!drag.active) {
      if (Math.abs(x) < 8 || Math.abs(x) <= Math.abs(y)) return
      drag.active = true
      scene.dataset.sealDragging = ''
      scene.setPointerCapture(event.pointerId)
    }
    queue(() => rotate(7 - Math.max(-12, Math.min(12, y * .2)),
      -10 + Math.max(-28, Math.min(28, x * .35))))
  }

  function finish() {
    const id = drag?.id
    drag = undefined
    delete scene.dataset.sealDragging
    if (id !== undefined && scene.hasPointerCapture(id)) scene.releasePointerCapture(id)
    resetRotation()
  }

  function release(event: PointerEvent) {
    if (event.pointerId === drag?.id) finish()
  }

  hero.addEventListener('pointermove', hover, { passive: true })
  scene.addEventListener('pointerleave', () => { if (!drag) resetRotation() }, options)
  scene.addEventListener('pointerdown', start, options)
  scene.addEventListener('pointermove', move, options)
  scene.addEventListener('pointerup', release, options)
  scene.addEventListener('pointercancel', release, options)
  scene.addEventListener('lostpointercapture', release, options)
  document.addEventListener('visibilitychange', () => { if (document.hidden) finish() }, options)

  return () => {
    hero.removeEventListener('pointermove', hover)
    events.abort()
    finish()
  }
}
