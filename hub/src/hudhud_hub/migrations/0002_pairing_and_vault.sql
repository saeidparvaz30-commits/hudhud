-- SPDX-License-Identifier: AGPL-3.0-or-later

CREATE TABLE pairing_codes (
  code_hash TEXT PRIMARY KEY,
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE vault_notes (
  book_id TEXT PRIMARY KEY REFERENCES books(id),
  path TEXT NOT NULL,
  region_hash TEXT NOT NULL
);
