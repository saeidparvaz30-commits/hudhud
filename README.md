# Hudhud

A self-hosted, open-source book reader that remembers where you stopped, feels
like paper, turns highlights into Obsidian notes, and, when you select a
passage, finds what you wrote about the same idea in other books.

Hudhud is the hoopoe. In Attar's *Conference of the Birds* it guides the other
birds to the Simorgh.

## Status

Early development. The hub's core modules exist and are tested:

| Module | Does |
|---|---|
| `library.py` | Imports EPUB, PDF, MOBI, AZW3, FB2, CBZ and TXT: format detection, DRM rejection, metadata, covers, content addressing |
| `db.py` | SQLite connection, migrations, ULIDs, tombstones |
| `progress.py` | Per-device reading positions and the resume rule |
| `vault.py` | Writes highlights into a managed region of an Obsidian note |

Search, sync, the HTTP API and the reader client come next.

## Layout

    hub/         Python hub (uv project): src/hudhud_hub/, tests/
    LICENSE      AGPL-3.0-or-later
    CLA.md       contributor licence agreement

## Development

    uv sync --project hub
    uv run --project hub pytest hub/tests
    uv run --project hub ruff check .

## Licence

AGPL-3.0-or-later. Outside contributions need the [CLA](CLA.md).
