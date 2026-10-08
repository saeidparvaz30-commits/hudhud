// SPDX-License-Identifier: AGPL-3.0-or-later
import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createHighlight, saveProgress } from './actions'
import { clearAll, db, getCursor, resetSyncedData, setCursor, setPairing } from './db'
import { onNotice } from './notices'
import { syncNow } from './sync'
import type { Book, Change } from './types'

const HUB = 'http://hub.test'
const BOOK: Book = { id: 'a'.repeat(64), title: 'Masnavi', author: 'Rumi', language: 'fa',
                     format: 'epub', file_size: 1, has_cover: false, deleted: false,
                     added_at: '2026-10-08T10:00:00.000Z', updated_at: '2026-10-08T10:00:00.000Z' }

type Handler = (url: URL, init?: RequestInit) => unknown
let routes: Record<string, Handler>
let calls: { path: string; body: unknown; keepalive?: boolean }[]

beforeEach(async () => {
  await clearAll()
  await setPairing({ hubUrl: HUB, token: 't', deviceId: 'pc', deviceName: 'PC' })
  calls = []
  routes = {
    '/sync/push': (_, init) => ({
      results: (JSON.parse(String(init?.body)).changes as Change[])
        .map((_c, index) => ({ index, status: 'accepted' })),
    }),
    '/sync/pull': () => ({ changes: [], cursor: 0, more: false, latest: 0 }),
  }
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input)
    calls.push({ path: url.pathname, body: init?.body ? JSON.parse(String(init.body)) : undefined,
                 keepalive: init?.keepalive })
    return new Response(JSON.stringify(routes[url.pathname](url, init)), { status: 200 })
  }))
})

afterEach(() => vi.unstubAllGlobals())

const settle = () => new Promise((r) => setTimeout(r, 50))

describe('progress', () => {
  it('reaches the hub right after it is saved, not on the next timer', async () => {
    await saveProgress(BOOK.id, 'epubcfi(/6/4!/4/2/1:3)', 0.42)
    await settle()
    await syncNow()
    const pushed = calls.filter((c) => c.path === '/sync/push')
      .flatMap((c) => (c.body as { changes: Change[] }).changes)
    expect(pushed.map((c) => c.entity)).toContain('progress')
  })

  it('can push with keepalive so a closing tab still delivers it', async () => {
    // A position saved while offline, still waiting in the outbox when the tab closes.
    await (await db()).add('outbox', { entity: 'progress', op: 'upsert',
                                       data: { book_id: BOOK.id, locator: 'cfi', fraction: 0.5 } })
    await syncNow({ keepalive: true })
    expect(calls.some((c) => c.path === '/sync/push' && c.keepalive)).toBe(true)
  })
})

describe('rejections', () => {
  it('tell the person instead of vanishing', async () => {
    const notices: string[] = []
    const stop = onNotice((n) => notices.push(n.message))
    routes['/sync/push'] = () => ({ results: [{ index: 0, status: 'rejected',
                                                reason: 'text is longer than 20000 characters' }] })
    await (await db()).add('outbox', { entity: 'highlight', op: 'upsert', data: { id: 'x' } })
    await syncNow()
    stop()
    expect(notices.join(' ')).toContain('text is longer than 20000 characters')
    expect(await (await db()).count('outbox')).toBe(0)
  })
})

describe('hub reset', () => {
  it('starts again from zero when the hub is behind our cursor', async () => {
    await setCursor(50)
    await (await db()).put('books', { ...BOOK, title: 'stale copy' })
    let pulls = 0
    routes['/sync/pull'] = (url) => {
      pulls++
      const since = Number(url.searchParams.get('since'))
      if (since === 50) return { changes: [], cursor: 50, more: false, latest: 3 }
      return { changes: [{ seq: 3, entity: 'book', entity_id: BOOK.id, op: 'upsert', data: BOOK,
                           device_id: 'phone', ts: BOOK.added_at }],
               cursor: 3, more: false, latest: 3 }
    }
    await syncNow()
    expect(pulls).toBe(2)
    expect(await getCursor()).toBe(3)
    expect((await (await db()).get('books', BOOK.id))?.title).toBe('Masnavi')
  })

  it('re-pairing clears synced data and the cursor but keeps unsent edits', async () => {
    await setCursor(800)
    await (await db()).put('books', BOOK)
    await (await db()).add('outbox', { entity: 'progress', op: 'upsert', data: {} })
    await resetSyncedData()
    expect(await getCursor()).toBe(0)
    expect(await (await db()).count('books')).toBe(0)
    expect(await (await db()).count('outbox')).toBe(1)
  })
})

describe('highlights', () => {
  it('refuses a selection longer than the hub accepts, before it is saved', async () => {
    await expect(createHighlight({ bookId: BOOK.id, locator: 'cfi', fraction: 0.1,
                                   text: 'x'.repeat(20_001), color: 'yellow' }))
      .rejects.toThrow(/too long/)
    expect(await (await db()).count('highlights')).toBe(0)
    expect(await (await db()).count('outbox')).toBe(0)
  })
})
