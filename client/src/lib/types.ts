// SPDX-License-Identifier: AGPL-3.0-or-later
export type BookFormat = 'epub' | 'pdf' | 'mobi' | 'azw3' | 'fb2' | 'cbz' | 'txt'

export interface Book {
  id: string
  title: string
  author: string | null
  language: string | null
  format: BookFormat
  file_size: number
  has_cover: boolean
  added_at: string
  updated_at: string
  deleted: boolean
}

export type HighlightColor = 'yellow' | 'green' | 'blue' | 'pink' | 'purple'

/** 'image' is a picture highlight: `text` holds its caption, the picture is stored apart. */
export type HighlightKind = 'text' | 'image'

export interface Highlight {
  id: string
  book_id: string
  locator: string
  fraction: number
  text: string
  color: HighlightColor
  comment: string
  created_at: string
  updated_at: string
  device_id: string
  deleted: boolean
  kind?: HighlightKind
}

export interface Progress {
  book_id: string
  device_id: string
  locator: string
  fraction: number
  updated_at: string
}

export type Entity = 'book' | 'progress' | 'highlight'

export interface Change {
  entity: Entity
  op: 'upsert' | 'delete'
  data: Record<string, unknown>
}

export interface PulledChange extends Change {
  seq: number
  entity_id: string
  device_id: string
  ts: string
}

/** One related passage found by the hub's semantic search. */
export interface SearchResult {
  kind: 'highlight' | 'vault'
  match: 'text' | 'note' | 'vault'
  score: number
  text: string
  book_id: string | null
  book_title: string | null
  highlight: (Pick<Highlight, 'id' | 'book_id' | 'locator' | 'fraction' | 'text' | 'comment'
                         | 'color'> & { kind: HighlightKind }) | null
  path: string | null
  obsidian_url: string | null
}

export interface Pairing {
  hubUrl: string
  token: string
  deviceId: string
  deviceName: string
}
