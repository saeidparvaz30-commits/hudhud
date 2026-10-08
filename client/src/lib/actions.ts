// SPDX-License-Identifier: AGPL-3.0-or-later
import { fetchBookFile, fetchCover, uploadBook } from './api'
import { commitLocal, db, getPairing } from './db'
import { ulid, utcNow } from './ids'
import { notifyData, syncNow } from './sync'
import type { Book, Highlight, HighlightColor, Pairing } from './types'

// The hub's limits (sync.py MAX_TEXT, MAX_LOCATOR): checked here so nothing is lost later.
const MAX_HIGHLIGHT_TEXT = 20_000
const MAX_LOCATOR = 4_000

async function requirePairing(): Promise<Pairing> {
  const pairing = await getPairing()
  if (!pairing) throw new Error('This device is not paired with a hub')
  return pairing
}

export async function saveProgress(bookId: string, locator: string, fraction: number) {
  const pairing = await requirePairing()
  const progress = { book_id: bookId, device_id: pairing.deviceId, locator,
                     fraction: Math.min(1, Math.max(0, fraction)), updated_at: utcNow() }
  await commitLocal({ entity: 'progress', op: 'upsert', data: { ...progress } },
                    (tx) => tx.objectStore('progress').put(progress))
  void syncNow()  // other devices should see where you stopped without waiting a minute
}

export async function createHighlight(input: { bookId: string; locator: string; fraction: number
                                               text: string; color: HighlightColor
                                               comment?: string }): Promise<Highlight> {
  const text = input.text.trim()
  if (text.length > MAX_HIGHLIGHT_TEXT || input.locator.length > MAX_LOCATOR) {
    throw new Error('That selection is too long to highlight. Try a shorter passage.')
  }
  const pairing = await requirePairing()
  const now = utcNow()
  const highlight: Highlight = {
    id: ulid(), book_id: input.bookId, locator: input.locator,
    fraction: Math.min(1, Math.max(0, input.fraction)), text,
    color: input.color, comment: input.comment ?? '', created_at: now, updated_at: now,
    device_id: pairing.deviceId, deleted: false,
  }
  await commitLocal({ entity: 'highlight', op: 'upsert', data: { ...highlight } },
                    (tx) => tx.objectStore('highlights').put(highlight))
  notifyData()
  void syncNow()  // spec 8: sync immediately after creating a highlight
  return highlight
}

export async function updateHighlight(highlight: Highlight,
                                      patch: Partial<Pick<Highlight, 'color' | 'comment'>>) {
  const pairing = await requirePairing()
  const next = { ...highlight, ...patch, updated_at: utcNow(), device_id: pairing.deviceId }
  await commitLocal({ entity: 'highlight', op: 'upsert', data: { ...next } },
                    (tx) => tx.objectStore('highlights').put(next))
  notifyData()
  void syncNow()
  return next
}

export async function deleteHighlight(highlight: Highlight) {
  const pairing = await requirePairing()
  const next = { ...highlight, deleted: true, updated_at: utcNow(), device_id: pairing.deviceId }
  await commitLocal({ entity: 'highlight', op: 'delete',
                      data: { id: next.id, updated_at: next.updated_at } },
                    (tx) => tx.objectStore('highlights').put(next))
  notifyData()
  void syncNow()
}

export async function deleteBook(book: Book) {
  const next = { ...book, deleted: true, updated_at: utcNow() }
  await commitLocal({ entity: 'book', op: 'delete',
                      data: { id: book.id, updated_at: next.updated_at } },
                    (tx) => tx.objectStore('books').put(next))
  await (await db()).delete('files', book.id)
  notifyData()
  void syncNow()
}

export interface ImportResult { name: string; book?: Book; error?: string }

/** Upload files to the hub. Imports need the hub: it hashes, validates and stores books. */
export async function importFiles(files: File[]): Promise<ImportResult[]> {
  const pairing = await requirePairing()
  const results: ImportResult[] = []
  for (const file of files) {
    try {
      const book = await uploadBook(pairing, file)
      const d = await db()
      await d.put('books', book)
      await d.put('files', file, book.id)
      results.push({ name: file.name, book })
    } catch (e) {
      results.push({ name: file.name, error: e instanceof Error ? e.message : String(e) })
    }
  }
  notifyData()
  void syncNow()
  return results
}

/** The book's bytes: from the local cache, else fetched once from the hub (immutable). */
export async function getBookFile(book: Book): Promise<Blob> {
  const d = await db()
  const cached = await d.get('files', book.id)
  if (cached) return cached
  const blob = await fetchBookFile(await requirePairing(), book.id)
  await d.put('files', blob, book.id)
  return blob
}

const coverUrls = new Map<string, string>()

export async function getCoverUrl(book: Book): Promise<string | null> {
  if (!book.has_cover) return null
  const known = coverUrls.get(book.id)
  if (known) return known
  const d = await db()
  let blob = await d.get('covers', book.id)
  if (!blob) {
    try {
      blob = await fetchCover(await requirePairing(), book.id)
      await d.put('covers', blob, book.id)
    } catch {
      return null
    }
  }
  const url = URL.createObjectURL(blob)
  coverUrls.set(book.id, url)
  return url
}
