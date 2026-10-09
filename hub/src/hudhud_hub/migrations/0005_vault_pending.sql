-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Books whose vault note is due, so a hub that was killed mid-debounce catches up on start.

CREATE TABLE vault_pending (book_id TEXT PRIMARY KEY);
