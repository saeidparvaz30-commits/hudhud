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

export interface Pairing {
  hubUrl: string
  token: string
  deviceId: string
  deviceName: string
}
