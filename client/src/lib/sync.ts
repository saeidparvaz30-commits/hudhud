// SPDX-License-Identifier: AGPL-3.0-or-later
import { ApiError, pullChanges, pushChanges } from './api'
import { db, getCursor, getPairing, setCursor } from './db'
import { mergeHighlight } from './merge'
import type { Book, Highlight, Pairing, Progress, PulledChange } from './types'

export type SyncState = 'idle' | 'syncing' | 'offline' | 'unpaired' | 'error'

const PUSH_BATCH = 200
const listeners = new Set<(state: SyncState) => void>()
let state: SyncState = 'idle'
let running: Promise<void> | null = null
let again = false
let backoff = 0
let retryTimer: ReturnType<typeof setTimeout> | undefined

function setState(next: SyncState) {
  state = next
  for (const listener of listeners) listener(next)
}

export function syncState(): SyncState {
  return state
}

export function onSync(listener: (state: SyncState) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Data changed locally or remotely; screens re-read IndexedDB when this fires. */
export const dataChanged = new EventTarget()

function notifyData() {
  dataChanged.dispatchEvent(new Event('change'))
}

async function pushOutbox(pairing: Pairing): Promise<void> {
  const d = await db()
  for (;;) {
    const keys = (await d.getAllKeys('outbox')).slice(0, PUSH_BATCH)
    if (keys.length === 0) return
    const changes = await Promise.all(keys.map((k) => d.get('outbox', k)))
    const { results } = await pushChanges(pairing, changes.filter((c) => c !== undefined))
    const tx = d.transaction('outbox', 'readwrite')
    for (const result of results) {
      // Accepted and ignored are both settled: the pull brings the hub's winner.
      if (result.status === 'rejected') console.warn('hub rejected a change:', result.reason)
      await tx.store.delete(keys[result.index])
    }
    await tx.done
  }
}

export async function applyRemote(changes: PulledChange[]): Promise<void> {
  const d = await db()
  const tx = d.transaction(['books', 'highlights', 'progress'], 'readwrite')
  for (const change of changes) {
    if (change.entity === 'book') {
      await tx.objectStore('books').put(change.data as unknown as Book)
    } else if (change.entity === 'highlight') {
      const remote = change.data as unknown as Highlight
      const local = await tx.objectStore('highlights').get(remote.id)
      await tx.objectStore('highlights').put(mergeHighlight(local, remote))
    } else if (change.entity === 'progress') {
      const remote = change.data as unknown as Progress
      const local = await tx.objectStore('progress').get([remote.book_id, remote.device_id])
      if (!local || remote.updated_at > local.updated_at) {
        await tx.objectStore('progress').put(remote)
      }
    }
  }
  await tx.done
}

async function pullAll(pairing: Pairing): Promise<boolean> {
  let cursor = await getCursor()
  let changed = false
  for (;;) {
    const page = await pullChanges(pairing, cursor)
    if (page.changes.length) {
      await applyRemote(page.changes)
      changed = true
    }
    cursor = page.cursor
    await setCursor(cursor)
    if (!page.more) return changed
  }
}

async function runOnce(): Promise<void> {
  const pairing = await getPairing()
  if (!pairing) {
    setState('unpaired')
    return
  }
  setState('syncing')
  try {
    await pushOutbox(pairing)
    if (await pullAll(pairing)) notifyData()
    backoff = 0
    setState('idle')
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      setState('unpaired')
      return
    }
    setState(e instanceof ApiError && e.status === 0 ? 'offline' : 'error')
    backoff = Math.min(backoff ? backoff * 2 : 5_000, 300_000)  // spec 12: cap 5 min
    clearTimeout(retryTimer)
    retryTimer = setTimeout(() => void syncNow(), backoff)
  }
}

/** Push the outbox and pull new changes. Concurrent calls coalesce into one extra run. */
export function syncNow(): Promise<void> {
  if (running) {
    again = true
    return running
  }
  running = (async () => {
    do {
      again = false
      await runOnce()
    } while (again)
  })().finally(() => {
    running = null
  })
  return running
}

/** Spec 8 triggers: app open, window focus, every 60 s while online. */
export function startAutoSync(): () => void {
  const onFocus = () => void syncNow()
  const onOnline = () => void syncNow()
  window.addEventListener('focus', onFocus)
  window.addEventListener('online', onOnline)
  const interval = setInterval(() => {
    if (navigator.onLine) void syncNow()
  }, 60_000)
  void syncNow()
  return () => {
    window.removeEventListener('focus', onFocus)
    window.removeEventListener('online', onOnline)
    clearInterval(interval)
  }
}

export { notifyData }
