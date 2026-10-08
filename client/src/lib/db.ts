// SPDX-License-Identifier: AGPL-3.0-or-later
import { type DBSchema, type IDBPDatabase, type IDBPTransaction, openDB } from 'idb'

import type { Book, Change, Highlight, Pairing, Progress } from './types'

interface HudhudDB extends DBSchema {
  books: { key: string; value: Book }
  files: { key: string; value: Blob }
  covers: { key: string; value: Blob }
  progress: { key: [string, string]; value: Progress; indexes: { by_book: string } }
  highlights: { key: string; value: Highlight; indexes: { by_book: string } }
  outbox: { key: number; value: Change }
  meta: { key: string; value: unknown }
}

let dbPromise: Promise<IDBPDatabase<HudhudDB>> | null = null

export function db(): Promise<IDBPDatabase<HudhudDB>> {
  dbPromise ??= openDB<HudhudDB>('hudhud', 1, {
    upgrade(d) {
      d.createObjectStore('books', { keyPath: 'id' })
      d.createObjectStore('files')
      d.createObjectStore('covers')
      d.createObjectStore('progress', { keyPath: ['book_id', 'device_id'] })
        .createIndex('by_book', 'book_id')
      d.createObjectStore('highlights', { keyPath: 'id' }).createIndex('by_book', 'book_id')
      d.createObjectStore('outbox', { autoIncrement: true })
      d.createObjectStore('meta')
    },
  })
  return dbPromise
}

export async function getPairing(): Promise<Pairing | undefined> {
  return (await (await db()).get('meta', 'pairing')) as Pairing | undefined
}

export async function setPairing(pairing: Pairing | undefined): Promise<void> {
  const d = await db()
  if (pairing) await d.put('meta', pairing, 'pairing')
  else await d.delete('meta', 'pairing')
}

export async function getCursor(): Promise<number> {
  return ((await (await db()).get('meta', 'cursor')) as number | undefined) ?? 0
}

export async function setCursor(cursor: number): Promise<void> {
  await (await db()).put('meta', cursor, 'cursor')
}

export async function listBooks(): Promise<Book[]> {
  const books = await (await db()).getAll('books')
  return books.filter((b) => !b.deleted).sort((a, b) => b.added_at.localeCompare(a.added_at))
}

export async function getBook(id: string): Promise<Book | undefined> {
  return (await db()).get('books', id)
}

export async function bookHighlights(bookId: string): Promise<Highlight[]> {
  const all = await (await db()).getAllFromIndex('highlights', 'by_book', bookId)
  return all.filter((h) => !h.deleted).sort((a, b) => a.fraction - b.fraction)
}

export async function bookProgress(bookId: string): Promise<Progress[]> {
  return (await db()).getAllFromIndex('progress', 'by_book', bookId)
}

export type LocalTx = IDBPTransaction<
  HudhudDB, ['books', 'highlights', 'progress', 'outbox'], 'readwrite'>

/** Write a local mutation and queue it for the hub in one transaction (spec 8, step 2). */
export async function commitLocal(change: Change,
                                  apply: (tx: LocalTx) => Promise<unknown>): Promise<void> {
  const d = await db()
  const tx = d.transaction(['books', 'highlights', 'progress', 'outbox'], 'readwrite')
  await apply(tx)
  await tx.objectStore('outbox').add(change)
  await tx.done
}

/** Forget everything local (used when unpairing). */
export async function clearAll(): Promise<void> {
  const d = await db()
  for (const store of ['books', 'files', 'covers', 'progress', 'highlights', 'outbox',
                       'meta'] as const) {
    await d.clear(store)
  }
}
