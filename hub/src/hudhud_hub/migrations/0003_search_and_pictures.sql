-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Picture highlights, and embeddings stored with their chunks (searched in memory).

ALTER TABLE highlights ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'
  CHECK (kind IN ('text', 'image'));

-- A highlight has a 'text' chunk and, if it has a note, a 'note' chunk; vault notes
-- are 'vault' chunks.
ALTER TABLE chunks ADD COLUMN field TEXT NOT NULL DEFAULT 'text';
ALTER TABLE chunks ADD COLUMN embedding BLOB;
CREATE UNIQUE INDEX chunks_identity ON chunks(source_kind, source_ref, field);
