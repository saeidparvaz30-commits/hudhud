-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Convention: no BEGIN/COMMIT in migration files. The runner wraps each file
-- in one transaction together with its schema_version row.
-- vec_chunks (sqlite-vec) arrives in a later migration with notebook 06.

CREATE TABLE books (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT,
  language TEXT,
  format TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  cover_path TEXT,
  added_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE progress (
  book_id TEXT NOT NULL REFERENCES books(id),
  device_id TEXT NOT NULL,
  locator TEXT NOT NULL,
  fraction REAL NOT NULL CHECK (fraction BETWEEN 0 AND 1),
  updated_at TEXT NOT NULL,
  PRIMARY KEY (book_id, device_id)
);

CREATE TABLE highlights (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id),
  locator TEXT NOT NULL,
  fraction REAL NOT NULL CHECK (fraction BETWEEN 0 AND 1),
  text TEXT NOT NULL,
  color TEXT NOT NULL DEFAULT 'yellow',
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  device_id TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX highlights_by_book ON highlights(book_id, deleted);

CREATE TABLE devices (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  paired_at TEXT NOT NULL,
  last_seen TEXT
);

CREATE TABLE changes (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  entity TEXT NOT NULL CHECK (entity IN ('book', 'progress', 'highlight')),
  entity_id TEXT NOT NULL,
  op TEXT NOT NULL CHECK (op IN ('upsert', 'delete')),
  payload TEXT NOT NULL,
  device_id TEXT NOT NULL,
  ts TEXT NOT NULL
);

CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('highlight', 'vault')),
  source_ref TEXT NOT NULL,
  book_id TEXT,
  text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  model TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX chunks_by_source ON chunks(source_kind, source_ref);
