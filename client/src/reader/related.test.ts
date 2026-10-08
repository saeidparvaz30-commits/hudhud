// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import type { SearchResult } from '../lib/types'
import { linkFor } from './related'

const base: SearchResult = { kind: 'highlight', match: 'note', score: 0.6, text: 't', book_id: 'b',
                             book_title: 'The Black Swan', highlight: null, path: null,
                             obsidian_url: null }

describe('linkFor', () => {
  it('links a highlight by its Obsidian block id', () => {
    const result = { ...base, highlight: { id: '01JB7X3K9Q2M4N5P6R7S8T9V0W', book_id: 'b', locator: 'c',
                                           fraction: 0, text: 't', comment: '', color: 'yellow' as const,
                                           kind: 'text' as const } }
    expect(linkFor(result)).toBe('[[The Black Swan#^h-01jb7x3k9q2m4n5p6r7s8t9v0w]]')
  })
  it('links a vault note by its path', () => {
    expect(linkFor({ ...base, kind: 'vault', match: 'vault', path: 'Ideas/Stories.md' }))
      .toBe('[[Ideas/Stories]]')
  })
})
