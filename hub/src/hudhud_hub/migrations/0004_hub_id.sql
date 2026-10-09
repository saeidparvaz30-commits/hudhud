-- SPDX-License-Identifier: AGPL-3.0-or-later
-- A stable identity, so a device that lost the hub's address can find it on the LAN again.

CREATE TABLE hub_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO hub_meta (key, value) VALUES ('hub_id', lower(hex(randomblob(16))));
