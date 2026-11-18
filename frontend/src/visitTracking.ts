import { onUnmounted } from 'vue'
import { api } from './api'

const heartbeatInterval = 30_000

let visitorId: Promise<string> | undefined

function storedVisitor(): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!globalThis.crypto?.randomUUID || !globalThis.indexedDB) {
      reject(new Error('Visitor storage unavailable'))
      return
    }
    const database = indexedDB.open('gduf-visits', 1)
    database.onupgradeneeded = () => database.result.createObjectStore('identity')
    database.onerror = () => reject(database.error)
    database.onsuccess = () => {
      const db = database.result
      const transaction = db.transaction('identity', 'readwrite')
      const identity = transaction.objectStore('identity')
      const request = identity.get('visitor')
      let id: string
      request.onsuccess = () => {
        id = request.result ?? crypto.randomUUID()
        if (request.result === undefined) identity.put(id, 'visitor')
      }
      transaction.oncomplete = () => {
        db.close()
        resolve(id)
      }
      transaction.onabort = () => {
        db.close()
        reject(transaction.error)
      }
    }
  })
}

export function useVisitTracking(enabled: boolean) {
  let view = { path: '', ready: false, counted: false }
  let timer: number | undefined
  let heartbeatInFlight = false

  async function report() {
    const current = view
    try {
      const id = await (visitorId ??= storedVisitor().catch(error => {
        visitorId = undefined
        throw error
      }))
      if (current !== view || !current.ready || document.hidden) return
      if (!current.counted) {
        current.counted = true
        await api('/visits', 'POST', { visitor_id: id, kind: 'page_view' })
      } else if (!heartbeatInFlight) {
        heartbeatInFlight = true
        try {
          await api('/visits', 'POST', { visitor_id: id, kind: 'heartbeat' })
        } finally {
          heartbeatInFlight = false
        }
      }
    } catch {
      // Collection is optional when storage or the network is unavailable.
    }
  }

  function pause() {
    window.clearInterval(timer)
    timer = undefined
  }

  function resume() {
    if (!view.ready || document.hidden || timer !== undefined) return
    void report()
    timer = window.setInterval(() => void report(), heartbeatInterval)
  }

  function updateVisibility() {
    if (document.hidden) pause()
    else resume()
  }

  if (enabled) document.addEventListener('visibilitychange', updateVisibility)
  onUnmounted(() => {
    pause()
    view.ready = false
    document.removeEventListener('visibilitychange', updateVisibility)
  })

  return {
    navigate(path: string) {
      pause()
      view = { path, ready: false, counted: false }
    },
    shown(path: string) {
      if (!enabled || view.path !== path || view.ready) return
      view.ready = true
      resume()
    },
    unavailable(path: string) {
      if (view.path !== path) return
      view.ready = false
      pause()
    },
  }
}
