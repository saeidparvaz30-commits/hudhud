// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { ulid, utcNow } from './ids'
import { mergeHighlight, newer, shouldOfferResume } from './merge'
import type { Highlight, Progress } from './types'

const base: Highlight = {
  id: '01JB7X3K9Q2M4N5P6R7S8T9V0W', book_id: 'a'.repeat(64), locator: 'cfi', fraction: 0.4,
  text: 'text', color: 'yellow', comment: '', created_at: '2026-10-08T10:00:00.000Z',
  updated_at: '2026-10-08T10:00:00.000Z', device_id: 'pc', deleted: false,
}
const at = (updated_at: string, device_id = 'pc', extra: Partial<Highlight> = {}): Highlight =>
  ({ ...base, updated_at, device_id, ...extra })

describe('newer', () => {
  it('orders by time, then by device id', () => {
    expect(newer(at('2026-10-08T11:00:00.000Z'), at('2026-10-08T10:00:00.000Z'))).toBe(true)
    expect(newer(at('2026-10-08T10:00:00.000Z', 'b'), at('2026-10-08T10:00:00.000Z', 'a'))).toBe(true)
    expect(newer(at('2026-10-08T10:00:00.000Z', 'a'), at('2026-10-08T10:00:00.000Z', 'a'))).toBe(false)
  })
})

describe('mergeHighlight', () => {
  it('takes the remote copy when nothing is local', () => {
    expect(mergeHighlight(undefined, base)).toBe(base)
  })
  it('keeps the newer copy', () => {
    const local = at('2026-10-08T12:00:00.000Z', 'pc', { comment: 'local' })
    const remote = at('2026-10-08T11:00:00.000Z', 'phone', { comment: 'remote' })
    expect(mergeHighlight(local, remote).comment).toBe('local')
    expect(mergeHighlight(remote, local).comment).toBe('local')
  })
  it('never resurrects a tombstone', () => {
    const deleted = at('2026-10-08T10:00:00.000Z', 'pc', { deleted: true })
    const edit = at('2026-10-08T12:00:00.000Z', 'phone', { comment: 'late edit' })
    expect(mergeHighlight(deleted, edit).deleted).toBe(true)
    expect(mergeHighlight(edit, deleted).deleted).toBe(true)
  })
})

describe('shouldOfferResume', () => {
  const p = (device_id: string, fraction: number, updated_at: string): Progress =>
    ({ book_id: 'b', device_id, locator: 'cfi', fraction, updated_at })
  const early = '2026-10-08T10:00:00.000Z'
  const late = '2026-10-08T11:00:00.000Z'

  it('follows the spec rule', () => {
    expect(shouldOfferResume(undefined, undefined, 300)).toBe(false)
    expect(shouldOfferResume(undefined, p('phone', 0.63, late), 300)).toBe(true)
    expect(shouldOfferResume(p('pc', 0.2, early), p('phone', 0.63, late), 300)).toBe(true)
    expect(shouldOfferResume(p('pc', 0.5, early), p('phone', 0.502, late), 300)).toBe(false)
    expect(shouldOfferResume(p('pc', 0.2, late), p('phone', 0.63, early), 300)).toBe(false)
  })
  it('treats a missing page count as one page', () => {
    expect(shouldOfferResume(undefined, p('phone', 0.5, late), 0)).toBe(false)
    expect(shouldOfferResume(undefined, p('phone', 1, late), 0)).toBe(false)
  })
})

describe('ids', () => {
  it('makes 26-character Crockford ULIDs that sort by time', () => {
    const a = ulid(Date.UTC(2026, 9, 8, 10))
    const b = ulid(Date.UTC(2026, 9, 8, 11))
    expect(a).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/)
    expect(a < b).toBe(true)
    expect(new Set(Array.from({ length: 200 }, () => ulid())).size).toBe(200)
  })
  it('formats timestamps the way the hub validates them', () => {
    expect(utcNow(new Date(Date.UTC(2026, 9, 8, 10, 0, 0, 5)))).toBe('2026-10-08T10:00:00.005Z')
  })
})
