// SPDX-License-Identifier: AGPL-3.0-or-later
import type { SearchResult } from '../lib/types'

export interface RelatedState {
  query: string
  results: SearchResult[] | null  // null while searching
  error?: string
  /** Set when the search came from a fresh selection that "Link these" can highlight. */
  canLink: boolean
}

export const MATCH_LABEL = { text: 'Highlight', note: 'Your note', vault: 'Vault note' } as const

/** The wiki-link that points at a match, for "Link these". */
export function linkFor(result: SearchResult): string {
  if (result.highlight) {
    return `[[${result.book_title ?? 'Untitled'}#^h-${result.highlight.id.toLowerCase()}]]`
  }
  return `[[${(result.path ?? '').replace(/\.md$/, '')}]]`
}

