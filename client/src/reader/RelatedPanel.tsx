// SPDX-License-Identifier: AGPL-3.0-or-later
import { navigate } from '../lib/hooks'
import type { SearchResult } from '../lib/types'
import { HIGHLIGHT_CSS } from './foliate'
import { MATCH_LABEL, type RelatedState } from './related'

export function RelatedPanel({ state, onLink }: {
  state: RelatedState
  onLink(result: SearchResult): void
}) {
  return (
    <div className="p-1">
      <blockquote className="mx-2 mt-1 mb-3 border-s-4 border-accent/60 ps-3 font-serif text-sm text-muted line-clamp-4"
                  dir="auto">
        {state.query}
      </blockquote>
      {state.error && <p className="p-3 text-sm text-muted">{state.error}</p>}
      {!state.error && state.results === null && (
        <p className="p-3 text-sm text-muted">Looking through your other books and notes…</p>
      )}
      {state.results?.length === 0 && (
        <p className="p-3 text-sm text-muted">
          Nothing related yet. Highlights and notes from your other books, and notes in your
          vault, show up here.
        </p>
      )}
      <ul className="space-y-2">
        {state.results?.map((r) => {
          const key = r.highlight?.id ?? `${r.path}-${r.text.slice(0, 20)}`
          return (
            <li key={key} className="rounded-xl border border-rule bg-paper p-3">
              <div className="flex items-center justify-between gap-2 text-xs text-muted">
                <span className="truncate font-medium text-ink" dir="auto">
                  {r.book_title ?? r.path}
                </span>
                <span className="shrink-0 rounded-full bg-ink/5 px-2 py-0.5">{MATCH_LABEL[r.match]}</span>
              </div>
              {r.highlight ? (
                <>
                  <p className="mt-2 border-s-4 ps-2 font-serif text-sm leading-relaxed line-clamp-5"
                     style={{ borderColor: HIGHLIGHT_CSS[r.highlight.color] }} dir="auto">
                    {r.highlight.kind === 'image' ? `Picture: ${r.highlight.text}` : r.highlight.text}
                  </p>
                  {r.highlight.comment && (
                    <p className="mt-1.5 ps-3 text-xs whitespace-pre-wrap text-muted" dir="auto">
                      {r.highlight.comment}
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-2 text-sm leading-relaxed whitespace-pre-wrap line-clamp-6" dir="auto">
                  {r.text}
                </p>
              )}
              <div className="mt-2 flex flex-wrap gap-3 text-xs">
                {r.highlight && (
                  <button type="button" className="text-accent"
                          onClick={() => navigate(`/read/${r.highlight!.book_id}?h=${r.highlight!.id}`)}>
                    Open in book
                  </button>
                )}
                {r.obsidian_url && (
                  <a className="text-accent" href={r.obsidian_url}>Open in Obsidian</a>
                )}
                {state.canLink && (
                  <button type="button" className="text-accent" onClick={() => onLink(r)}>
                    Link these
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
