// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useRef, useState } from 'react'

import { Icon, IconButton } from '../components/Icon'
import { createHighlight, deleteHighlight, getBookFile, saveProgress,
         updateHighlight } from '../lib/actions'
import { listDevices } from '../lib/api'
import { bookHighlights, bookProgress, db, getBook, getPairing } from '../lib/db'
import { navigate, type ReadingPrefs, setPrefs, type Theme, useLive, usePrefs } from '../lib/hooks'
import { shouldOfferResume } from '../lib/merge'
import type { Highlight, HighlightColor, Progress } from '../lib/types'
import { bookCss, type FoliateView, HIGHLIGHT_CSS, loadFoliate, type RelocateDetail,
         type TocItem, toFoliateFile } from './foliate'
import { HighlightPopover, type PopoverTarget } from './HighlightPopover'

const THEME_COLORS: Record<Theme, { paper: string; ink: string; accent: string
                                    selection: string }> = {
  paper: { paper: '#f4ecd8', ink: '#3b2f2f', accent: '#8a5a2b', selection: '#e4cf9f' },
  sepia: { paper: '#e9d9b6', ink: '#4a3826', accent: '#8a4f1f', selection: '#d6bb84' },
  night: { paper: '#1c1a17', ink: '#d9cfbf', accent: '#d9a066', selection: '#5a4a32' },
}

type Overlayer = { highlight: unknown }
type Panel = null | 'toc' | 'highlights' | 'style'

function applyLayout(view: FoliateView, prefs: ReadingPrefs) {
  const r = view.renderer
  r.setAttribute('flow', 'paginated')
  r.setAttribute('margin', `${prefs.margin}px`)
  r.setAttribute('gap', '6%')
  r.setAttribute('max-inline-size', `${Math.round(660 * prefs.fontScale)}px`)
  r.setAttribute('max-column-count', '2')
  r.setStyles?.(bookCss({ fontScale: prefs.fontScale, lineHeight: prefs.lineHeight,
                          justify: prefs.justify, colors: THEME_COLORS[prefs.theme] }))
  view.style.setProperty('--overlayer-highlight-opacity', prefs.theme === 'night' ? '0.45' : '0.4')
  view.style.setProperty('--overlayer-highlight-blend-mode',
                         prefs.theme === 'night' ? 'normal' : 'multiply')
}

function frameOffset(doc: Document): { left: number; top: number; scale: number } {
  const frame = doc.defaultView?.frameElement as HTMLElement | null
  if (!frame) return { left: 0, top: 0, scale: 1 }
  const rect = frame.getBoundingClientRect()
  const scale = frame.offsetWidth ? rect.width / frame.offsetWidth : 1
  return { left: rect.left, top: rect.top, scale }
}

function TocList({ items, onPick, depth = 0 }: { items: TocItem[]; onPick(href: string): void
                                                  depth?: number }) {
  return (
    <ul>
      {items.map((item, i) => (
        <li key={`${item.href}-${i}`}>
          <button type="button" onClick={() => onPick(item.href)} dir="auto"
                  style={{ paddingInlineStart: `${0.75 + depth}rem` }}
                  className="block w-full rounded-md py-2 pe-3 text-start text-sm hover:bg-ink/5">
            {item.label?.trim() || 'Untitled'}
          </button>
          {item.subitems?.length ? <TocList items={item.subitems} onPick={onPick} depth={depth + 1} /> : null}
        </li>
      ))}
    </ul>
  )
}

export function Reader({ bookId, highlightId }: { bookId: string; highlightId?: string }) {
  const book = useLive(() => getBook(bookId), [bookId])
  const highlights = useLive(() => bookHighlights(bookId), [bookId])
  const prefs = usePrefs()
  const host = useRef<HTMLDivElement>(null)
  const viewRef = useRef<FoliateView | null>(null)
  const overlayer = useRef<Overlayer | null>(null)
  const highlightsRef = useRef<Highlight[]>([])
  const drawn = useRef(new Set<string>())
  const prefsRef = useRef(prefs)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pendingSave = useRef<RelocateDetail | null>(null)
  const annotationHit = useRef(false)

  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState('')
  const [location, setLocation] = useState<RelocateDetail | null>(null)
  const [toc, setToc] = useState<TocItem[]>([])
  const [panel, setPanel] = useState<Panel>(null)
  const [popover, setPopover] = useState<PopoverTarget | null>(null)
  const [resume, setResume] = useState<{ progress: Progress; device: string } | null>(null)
  const [chrome, setChrome] = useState(true)

  prefsRef.current = prefs

  const flushSave = useCallback(() => {
    clearTimeout(saveTimer.current)
    const detail = pendingSave.current
    pendingSave.current = null
    if (detail?.cfi) void saveProgress(bookId, detail.cfi, detail.fraction ?? 0)
  }, [bookId])

  const openPopover = useCallback((doc: Document, range: Range, data: Partial<PopoverTarget>) => {
    const rect = range.getBoundingClientRect()
    const { left, top, scale } = frameOffset(doc)
    setPopover({ x: left + (rect.left + rect.width / 2) * scale, top: top + rect.top * scale,
                 bottom: top + rect.bottom * scale, ...data })
  }, [])

  // Open the book once per id.
  useEffect(() => {
    if (!book || !host.current) return
    const container = host.current
    let cancelled = false
    let view: FoliateView | undefined

    const onKey = (e: KeyboardEvent) => {
      const v = viewRef.current
      if (!v || (e.target as HTMLElement | null)?.closest?.('input, textarea')) return
      if (['ArrowLeft', 'PageUp'].includes(e.key)) void v.goLeft()
      else if (['ArrowRight', 'PageDown', ' '].includes(e.key)) void v.goRight()
      else if (e.key === 'Escape') setPanel(null)
    }

    const attachDoc = (doc: Document, index: number) => {
      doc.addEventListener('keydown', onKey)
      let lastCfi = ''
      const checkSelection = () => {
        const sel = doc.getSelection()
        if (!sel || sel.isCollapsed || !sel.rangeCount || !view) return
        const text = sel.toString().trim()
        if (!text) return
        const range = sel.getRangeAt(0)
        const cfi = view.getCFI(index, range)
        if (cfi === lastCfi) return
        lastCfi = cfi
        openPopover(doc, range, { cfi, text })
      }
      let timer: ReturnType<typeof setTimeout> | undefined
      doc.addEventListener('pointerup', () => setTimeout(checkSelection, 20))
      doc.addEventListener('selectionchange', () => {
        clearTimeout(timer)
        if (doc.getSelection()?.isCollapsed) lastCfi = ''
        else timer = setTimeout(checkSelection, 500)  // touch: wait for the handles to settle
      })
      doc.addEventListener('click', (e) => {
        setTimeout(() => {
          if (annotationHit.current) {
            annotationHit.current = false
            return
          }
          if (!doc.getSelection()?.isCollapsed) return
          if ((e.target as Element | null)?.closest?.('a')) return
          const { left, scale } = frameOffset(doc)
          const box = container.getBoundingClientRect()
          const ratio = (left + e.clientX * scale - box.left) / box.width
          if (ratio < 0.22) void view?.goLeft()
          else if (ratio > 0.78) void view?.goRight()
          else setChrome((c) => !c)
        }, 0)
      })
    }

    ;(async () => {
      try {
        const { Overlayer } = await loadFoliate()
        overlayer.current = Overlayer
        const file = await toFoliateFile(book, await getBookFile(book))
        if (cancelled) return
        view = document.createElement('foliate-view') as FoliateView
        view.style.cssText = 'display:block;width:100%;height:100%'
        container.append(view)
        await view.open(file)
        if (cancelled) return
        viewRef.current = view
        setToc(view.book.toc ?? [])

        view.addEventListener('relocate', (e) => {
          const detail = (e as CustomEvent<RelocateDetail>).detail
          setLocation(detail)
          pendingSave.current = detail
          clearTimeout(saveTimer.current)
          saveTimer.current = setTimeout(flushSave, 1500)
        })
        view.addEventListener('load', (e) => {
          const { doc, index } = (e as CustomEvent<{ doc: Document; index: number }>).detail
          attachDoc(doc, index)
        })
        view.addEventListener('create-overlay', (e) => {
          const { index } = (e as CustomEvent<{ index: number }>).detail
          for (const h of highlightsRef.current) {
            try {
              if (view!.resolveCFI(h.locator).index === index) {
                void view!.addAnnotation({ value: h.locator, color: h.color })
              }
            } catch {
              /* a locator this rendition cannot resolve */
            }
          }
        })
        view.addEventListener('draw-annotation', (e) => {
          const { draw, annotation } = (e as CustomEvent<{
            draw(fn: unknown, opts: unknown): void; annotation: { color?: string } }>).detail
          draw(overlayer.current?.highlight, {
            color: HIGHLIGHT_CSS[annotation.color ?? 'yellow'] ?? HIGHLIGHT_CSS.yellow })
        })
        view.addEventListener('show-annotation', (e) => {
          const { value, range } = (e as CustomEvent<{ value: string; range: Range }>).detail
          const existing = highlightsRef.current.find((h) => h.locator === value)
          if (!existing) return
          annotationHit.current = true
          openPopover(range.startContainer.ownerDocument!, range, { existing })
        })

        applyLayout(view, prefsRef.current)
        if (view.isFixedLayout) container.classList.add('paper-tint')

        const pairing = await getPairing()
        const progress = await bookProgress(bookId)
        const own = progress.find((p) => p.device_id === pairing?.deviceId)
        const jump = highlightId ? (await (await db()).get('highlights', highlightId))?.locator : undefined
        const start = jump ?? own?.locator
        await view.init({ lastLocation: start ?? null, showTextStart: !start })
        if (cancelled) return
        setStatus('ready')

        if (!jump && pairing) {
          const other = progress.filter((p) => p.device_id !== pairing.deviceId)
            .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]
          const pages = view.lastLocation?.location?.total ?? 300
          if (shouldOfferResume(own, other, pages)) {
            let device = 'another device'
            try {
              device = (await listDevices(pairing)).find((d) => d.id === other.device_id)?.name ?? device
            } catch {
              /* offline: generic label */
            }
            if (!cancelled) setResume({ progress: other, device })
          }
        }
      } catch (e) {
        console.error(e)
        if (!cancelled) {
          setStatus('error')
          setError(e instanceof Error ? e.message : String(e))
        }
      }
    })()

    window.addEventListener('keydown', onKey)
    const onHide = () => document.visibilityState === 'hidden' && flushSave()
    document.addEventListener('visibilitychange', onHide)
    return () => {
      cancelled = true
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('visibilitychange', onHide)
      flushSave()
      view?.close()
      view?.remove()
      viewRef.current = null
      drawn.current.clear()
      container.classList.remove('paper-tint')
    }
    // Re-open only when the book itself changes, not on every metadata refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [book?.id])

  // Keep drawn annotations in step with local edits and synced changes.
  useEffect(() => {
    highlightsRef.current = highlights ?? []
    const view = viewRef.current
    if (!view || status !== 'ready') return
    const live = new Map((highlights ?? []).map((h) => [h.locator, h]))
    for (const locator of drawn.current) {
      if (!live.has(locator)) void view.deleteAnnotation({ value: locator })
    }
    for (const h of live.values()) void view.addAnnotation({ value: h.locator, color: h.color })
    drawn.current = new Set(live.keys())
  }, [highlights, status])

  useEffect(() => {
    if (viewRef.current && status === 'ready') applyLayout(viewRef.current, prefs)
  }, [prefs, status])

  function clearSelections() {
    for (const frame of host.current?.querySelector('foliate-view')?.shadowRoot
      ?.querySelectorAll('iframe') ?? []) {
      frame.contentDocument?.getSelection()?.removeAllRanges()
    }
  }

  async function onCreate(color: HighlightColor, comment: string) {
    const target = popover
    setPopover(null)
    if (!target?.cfi || !target.text) return
    await createHighlight({ bookId, locator: target.cfi, text: target.text, color, comment,
                            fraction: viewRef.current?.lastLocation?.fraction ?? 0 })
    clearSelections()
  }

  async function onUpdate(h: Highlight, patch: { color?: HighlightColor; comment?: string }) {
    setPopover(null)
    await updateHighlight(h, patch)
  }

  async function onDelete(h: Highlight) {
    setPopover(null)
    await deleteHighlight(h)
  }

  const percent = Math.round((location?.fraction ?? 0) * 100)
  const bar = `relative z-20 flex items-center gap-1 px-2 transition-opacity duration-200 ${chrome ? 'opacity-100' : 'pointer-events-none opacity-0'}`

  return (
    <div className="paper-grain flex h-full flex-col overflow-hidden">
      <header className={`${bar} h-14 border-b border-rule/60`}>
        <IconButton icon="back" label="Back to library" onClick={() => navigate('/')} />
        <p className="min-w-0 flex-1 truncate px-1 font-serif" dir="auto">{book?.title}</p>
        <IconButton icon="list" label="Contents" active={panel === 'toc'}
                    onClick={() => setPanel(panel === 'toc' ? null : 'toc')} />
        <IconButton icon="marker" label="Highlights" active={panel === 'highlights'}
                    onClick={() => setPanel(panel === 'highlights' ? null : 'highlights')} />
        <IconButton icon="type" label="Reading settings" active={panel === 'style'}
                    onClick={() => setPanel(panel === 'style' ? null : 'style')} />
      </header>

      <div className="relative min-h-0 flex-1">
        <div ref={host} className="absolute inset-0 z-10" />
        {status === 'loading' && (
          <p className="absolute inset-0 z-20 grid place-items-center text-muted">Opening…</p>
        )}
        {status === 'error' && (
          <div className="absolute inset-0 z-20 grid place-items-center p-6 text-center">
            <div>
              <p className="font-serif text-lg">This book could not be opened.</p>
              <p className="mt-1 text-sm text-muted">{error}</p>
            </div>
          </div>
        )}
        {resume && (
          <div role="status" className="absolute inset-x-0 top-3 z-30 mx-auto flex w-fit max-w-[92%] items-center gap-3 rounded-full border border-rule bg-raised px-4 py-2 text-sm shadow-lg">
            <span>Continue from {resume.device} at {Math.round(resume.progress.fraction * 100)}%?</span>
            <button type="button" className="font-medium text-accent" onClick={() => {
              void viewRef.current?.goTo(resume.progress.locator)
              setResume(null)
            }}>Continue</button>
            <button type="button" className="text-muted" onClick={() => setResume(null)}>Stay</button>
          </div>
        )}
        {panel && (
          <aside className="absolute inset-y-0 right-0 z-30 flex w-full max-w-sm flex-col border-l border-rule bg-raised shadow-xl">
            <div className="flex items-center justify-between border-b border-rule px-4 py-2">
              <h2 className="font-medium">
                {{ toc: 'Contents', highlights: 'Highlights', style: 'Reading' }[panel]}
              </h2>
              <IconButton icon="close" label="Close" onClick={() => setPanel(null)} />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {panel === 'toc' && (toc.length
                ? <TocList items={toc} onPick={(href) => { void viewRef.current?.goTo(href); setPanel(null) }} />
                : <p className="p-3 text-sm text-muted">This book has no table of contents.</p>)}
              {panel === 'highlights' && <HighlightList highlights={highlights ?? []}
                onPick={(h) => { void viewRef.current?.goTo(h.locator); setPanel(null) }}
                onDelete={(h) => void deleteHighlight(h)} />}
              {panel === 'style' && <StylePanel prefs={prefs} />}
            </div>
          </aside>
        )}
      </div>

      <footer className={`${bar} h-12 gap-3 border-t border-rule/60 px-4 text-xs text-muted`}>
        <button type="button" aria-label="Previous page" onClick={() => void viewRef.current?.goLeft()}
                className="grid h-8 w-8 place-items-center rounded-full hover:bg-ink/10">
          <Icon name="left" size={18} />
        </button>
        <input type="range" min={0} max={1} step={0.0005} value={location?.fraction ?? 0}
               aria-label="Position in book" className="min-w-0 flex-1 accent-[var(--accent)]"
               onChange={(e) => void viewRef.current?.goToFraction(Number(e.target.value))} />
        <span className="w-10 text-right tabular-nums">{percent}%</span>
        <span className="hidden max-w-[30%] truncate sm:inline" dir="auto">{location?.tocItem?.label}</span>
        <button type="button" aria-label="Next page" onClick={() => void viewRef.current?.goRight()}
                className="grid h-8 w-8 place-items-center rounded-full hover:bg-ink/10">
          <Icon name="right" size={18} />
        </button>
      </footer>

      {popover && <HighlightPopover target={popover} onCreate={(c, n) => void onCreate(c, n)}
                                    onUpdate={(h, p) => void onUpdate(h, p)}
                                    onDelete={(h) => void onDelete(h)}
                                    onClose={() => { setPopover(null); clearSelections() }} />}
    </div>
  )
}

function HighlightList({ highlights, onPick, onDelete }: {
  highlights: Highlight[]; onPick(h: Highlight): void; onDelete(h: Highlight): void
}) {
  if (!highlights.length) {
    return <p className="p-3 text-sm text-muted">Select text in the book to highlight it.</p>
  }
  return (
    <ul className="space-y-1">
      {highlights.map((h) => (
        <li key={h.id} className="group rounded-lg hover:bg-ink/5">
          <button type="button" onClick={() => onPick(h)} className="block w-full p-3 text-start">
            <p className="border-s-4 ps-2 font-serif text-sm leading-relaxed line-clamp-4" dir="auto"
               style={{ borderColor: HIGHLIGHT_CSS[h.color] }}>{h.text}</p>
            {h.comment && <p className="mt-1.5 ps-3 text-xs text-muted" dir="auto">{h.comment}</p>}
            <p className="mt-1 ps-3 text-xs text-muted">{Math.round(h.fraction * 100)}%</p>
          </button>
          <button type="button" onClick={() => onDelete(h)}
                  className="mb-2 ms-3 text-xs text-red-700 opacity-70 hover:opacity-100">Delete</button>
        </li>
      ))}
    </ul>
  )
}

function StylePanel({ prefs }: { prefs: ReadingPrefs }) {
  const step = (key: 'fontScale' | 'lineHeight' | 'margin', delta: number, min: number, max: number) =>
    setPrefs({ [key]: Math.round(Math.min(max, Math.max(min, prefs[key] + delta)) * 100) / 100 })
  const row = 'flex items-center justify-between px-3 py-3 text-sm'
  const btn = 'grid h-9 w-9 place-items-center rounded-full border border-rule hover:bg-ink/5'
  return (
    <div>
      <div className="flex gap-2 px-3 py-3">
        {(['paper', 'sepia', 'night'] as Theme[]).map((theme) => (
          <button key={theme} type="button" data-theme={theme} onClick={() => setPrefs({ theme })}
                  className={`h-12 flex-1 rounded-lg border-2 bg-paper text-sm capitalize text-ink ${prefs.theme === theme ? 'border-accent' : 'border-rule'}`}>
            {theme}
          </button>
        ))}
      </div>
      <div className={row}>
        <span>Text size</span>
        <span className="flex items-center gap-3">
          <button type="button" className={btn} aria-label="Smaller text" onClick={() => step('fontScale', -0.1, 0.7, 2)}>A-</button>
          <span className="w-10 text-center tabular-nums">{Math.round(prefs.fontScale * 100)}%</span>
          <button type="button" className={btn} aria-label="Larger text" onClick={() => step('fontScale', 0.1, 0.7, 2)}>A+</button>
        </span>
      </div>
      <div className={row}>
        <span>Line spacing</span>
        <span className="flex items-center gap-3">
          <button type="button" className={btn} aria-label="Tighter lines" onClick={() => step('lineHeight', -0.1, 1.1, 2.4)}>-</button>
          <span className="w-10 text-center tabular-nums">{prefs.lineHeight.toFixed(1)}</span>
          <button type="button" className={btn} aria-label="Looser lines" onClick={() => step('lineHeight', 0.1, 1.1, 2.4)}>+</button>
        </span>
      </div>
      <div className={row}>
        <span>Margins</span>
        <span className="flex items-center gap-3">
          <button type="button" className={btn} aria-label="Narrower margins" onClick={() => step('margin', -12, 0, 120)}>-</button>
          <span className="w-10 text-center tabular-nums">{prefs.margin}</span>
          <button type="button" className={btn} aria-label="Wider margins" onClick={() => step('margin', 12, 0, 120)}>+</button>
        </span>
      </div>
      <label className={`${row} cursor-pointer`}>
        <span>Justify text</span>
        <input type="checkbox" checked={prefs.justify} onChange={(e) => setPrefs({ justify: e.target.checked })}
               className="h-5 w-5 accent-[var(--accent)]" />
      </label>
    </div>
  )
}
