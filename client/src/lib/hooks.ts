// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

import { dataChanged, onSync, type SyncState, syncState } from './sync'

/** Re-runs `load` whenever local data changes (local edits or a sync pull). */
export function useLive<T>(load: () => Promise<T>, deps: unknown[]): T | undefined {
  const [value, setValue] = useState<T>()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps)
  useEffect(() => {
    let alive = true
    const refresh = () => void run().then((v) => alive && setValue(v))
    refresh()
    dataChanged.addEventListener('change', refresh)
    return () => {
      alive = false
      dataChanged.removeEventListener('change', refresh)
    }
  }, [run])
  return value
}

export function useSyncState(): SyncState {
  return useSyncExternalStore(onSync, syncState)
}

export type Route = { name: 'library' } | { name: 'reader'; bookId: string; highlight?: string }
  | { name: 'settings' }

function parse(): Route {
  const path = window.location.pathname
  const read = path.match(/^\/read\/([0-9a-f]{64})/)
  if (read) {
    const highlight = new URLSearchParams(window.location.search).get('h') ?? undefined
    return { name: 'reader', bookId: read[1], highlight }
  }
  if (path === '/settings') return { name: 'settings' }
  return { name: 'library' }
}

const routeListeners = new Set<() => void>()
let current = parse()

window.addEventListener('popstate', () => {
  current = parse()
  routeListeners.forEach((l) => l())
})

export function navigate(path: string, replace = false) {
  if (replace) window.history.replaceState(null, '', path)
  else window.history.pushState(null, '', path)
  current = parse()
  routeListeners.forEach((l) => l())
}

export function useRoute(): Route {
  return useSyncExternalStore(
    (l) => {
      routeListeners.add(l)
      return () => routeListeners.delete(l)
    },
    () => current,
  )
}

export type Theme = 'paper' | 'sepia' | 'night'

export interface ReadingPrefs {
  theme: Theme
  fontScale: number
  lineHeight: number
  margin: number
  justify: boolean
  /** PDFs and comics: how a page fits the screen, and one page or two side by side. */
  pageFit: 'fit-page' | 'fit-width'
  pageSpread: 'one' | 'two'
}

const DEFAULT_PREFS: ReadingPrefs = { theme: 'paper', fontScale: 1.1, lineHeight: 1.6,
                                      margin: 48, justify: true, pageFit: 'fit-page',
                                      pageSpread: 'two' }
const PREFS_KEY = 'hudhud.reading'

function loadPrefs(): ReadingPrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS
  } catch {
    return DEFAULT_PREFS
  }
}

const prefsListeners = new Set<() => void>()
let prefs = loadPrefs()

export function setPrefs(patch: Partial<ReadingPrefs>) {
  prefs = { ...prefs, ...patch }
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    /* private mode: keep in memory */
  }
  prefsListeners.forEach((l) => l())
}

export function usePrefs(): ReadingPrefs {
  const value = useSyncExternalStore(
    (l) => {
      prefsListeners.add(l)
      return () => prefsListeners.delete(l)
    },
    () => prefs,
  )
  useEffect(() => {
    document.documentElement.dataset.theme = value.theme
    const paper = getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', paper)
  }, [value.theme])
  return value
}
