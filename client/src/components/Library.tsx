// SPDX-License-Identifier: AGPL-3.0-or-later
import { type DragEvent, useEffect, useRef, useState } from 'react'

import { deleteBook, getCoverUrl, type ImportResult, importFiles } from '../lib/actions'
import { bookProgress, getPairing, listBooks } from '../lib/db'
import { navigate, useLive, useSyncState } from '../lib/hooks'
import type { Book } from '../lib/types'
import { Icon, IconButton } from './Icon'

const ACCEPT = '.epub,.pdf,.mobi,.azw3,.fb2,.cbz,.txt'

function SyncDot() {
  const state = useSyncState()
  const label = { idle: 'Synced', syncing: 'Syncing', offline: 'Offline', unpaired: 'Not paired',
                  error: 'Sync error' }[state]
  const color = { idle: 'bg-emerald-600', syncing: 'bg-amber-500 animate-pulse',
                  offline: 'bg-zinc-400', unpaired: 'bg-red-600', error: 'bg-red-600' }[state]
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted" title={label}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="hidden sm:inline">{label}</span>
    </span>
  )
}

function Cover({ book }: { book: Book }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    void getCoverUrl(book).then(setUrl)
  }, [book])
  if (url) {
    return <img src={url} alt="" className="h-full w-full object-cover" loading="lazy" />
  }
  return (
    <div className="flex h-full flex-col justify-between bg-accent/15 p-3 text-left" dir="auto">
      <span className="font-serif text-sm leading-snug line-clamp-5">{book.title}</span>
      {book.author && <span className="text-xs text-muted line-clamp-2">{book.author}</span>}
    </div>
  )
}

function BookCard({ book, fraction }: { book: Book; fraction: number }) {
  const [menu, setMenu] = useState(false)
  return (
    <li className="group relative">
      <button type="button" onClick={() => navigate(`/read/${book.id}`)}
              className="block w-full text-left">
        <div className="aspect-[2/3] overflow-hidden rounded-md border border-rule bg-raised shadow-sm transition group-hover:shadow-md">
          <Cover book={book} />
        </div>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-ink/10">
          <div className="h-full bg-accent" style={{ width: `${Math.round(fraction * 100)}%` }} />
        </div>
        <p className="mt-1.5 truncate font-serif text-sm" dir="auto">{book.title}</p>
        <p className="truncate text-xs text-muted" dir="auto">
          {book.author ?? book.format.toUpperCase()}
        </p>
      </button>
      <button type="button" aria-label="Book options" onClick={() => setMenu(!menu)}
              className="absolute top-1.5 right-1.5 grid h-8 w-8 place-items-center rounded-full bg-paper/85 opacity-100 shadow-sm sm:opacity-0 sm:group-hover:opacity-100">
        <Icon name="more" size={18} />
      </button>
      {menu && (
        <div className="absolute top-11 right-1.5 z-20 w-44 rounded-lg border border-rule bg-raised p-1 shadow-lg">
          <button type="button" onClick={() => { setMenu(false); void deleteBook(book) }}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-700 hover:bg-ink/5">
            <Icon name="trash" size={16} /> Remove from library
          </button>
        </div>
      )}
    </li>
  )
}

export function Library() {
  const books = useLive(async () => {
    const pairing = await getPairing()
    const list = await listBooks()
    return Promise.all(list.map(async (book) => {
      const progress = await bookProgress(book.id)
      const latest = progress.sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]
      const own = progress.find((p) => p.device_id === pairing?.deviceId)
      return { book, fraction: (own ?? latest)?.fraction ?? 0 }
    }))
  }, [])
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<ImportResult[]>([])

  async function upload(files: File[]) {
    if (!files.length) return
    setBusy(true)
    setResults(await importFiles(files))
    setBusy(false)
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    void upload(Array.from(event.dataTransfer.files))
  }

  const failures = results.filter((r) => r.error)

  return (
    <div className="paper-grain safe-x min-h-full"
         onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
         onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false) }}
         onDrop={onDrop}>
      <header className="relative z-10 mx-auto flex max-w-6xl items-center gap-3 px-4 pt-[calc(1.5rem+var(--safe-top))] pb-4 sm:px-8">
        <img src="/hudhud.svg" alt="" className="h-8 w-8" />
        <h1 className="font-serif text-2xl">Library</h1>
        <SyncDot />
        <div className="ml-auto flex items-center gap-1">
          <button type="button" onClick={() => input.current?.click()} disabled={busy}
                  className="flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-medium text-paper disabled:opacity-60">
            <Icon name="plus" size={18} /> {busy ? 'Importing…' : 'Import'}
          </button>
          <IconButton icon="gear" label="Settings" onClick={() => navigate('/settings')} />
        </div>
        <input ref={input} type="file" accept={ACCEPT} multiple hidden
               onChange={(e) => { void upload(Array.from(e.target.files ?? [])); e.target.value = '' }} />
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-[calc(4rem+var(--safe-bottom))] sm:px-8">
        {failures.length > 0 && (
          <div role="alert" className="mb-6 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">
            {failures.map((f) => <p key={f.name}><strong>{f.name}</strong>: {f.error}</p>)}
            <button type="button" className="mt-1 underline" onClick={() => setResults([])}>Dismiss</button>
          </div>
        )}
        {books === undefined ? null : books.length === 0 ? (
          <div className="mt-20 text-center text-muted">
            <p className="font-serif text-xl text-ink">Your shelf is empty</p>
            <p className="mt-2 text-sm">Import an EPUB, PDF, MOBI, AZW3, FB2, CBZ or TXT file, or drop one here.</p>
          </div>
        ) : (
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] gap-x-5 gap-y-8">
            {books.map(({ book, fraction }) => <BookCard key={book.id} book={book} fraction={fraction} />)}
          </ul>
        )}
      </main>

      {dragging && (
        <div className="pointer-events-none fixed inset-3 z-30 grid place-items-center rounded-2xl border-2 border-dashed border-accent bg-paper/80">
          <p className="font-serif text-xl">Drop books to import</p>
        </div>
      )}
    </div>
  )
}
