# Hudhud

A self-hosted, open-source book reader that remembers where you stopped, feels
like paper, turns highlights into Obsidian notes, and, when you select a
passage, finds what you wrote about the same idea in other books.

Hudhud is the hoopoe. In Attar's *Conference of the Birds* it guides the other
birds to the Simorgh.

## Status

Early but usable: a hub on your PC, a reader in any browser on PC and phone.

- Import EPUB, PDF, MOBI, AZW3, FB2, CBZ and TXT (DRM-free only).
- Paper, sepia and night themes; Literata and Vazirmatn; right-to-left text.
- Resume where you stopped, including "Continue from Phone at 63%?".
- Highlights with colours and notes, written to your Obsidian vault with
  linkable block IDs.
- Changes sync through the hub; each device keeps working offline and catches up.

Semantic search across your notes ("what did I write about this in other
books?") is next.

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm.

    pnpm --dir client install
    pnpm --dir client build
    uv run --project hub hudhud serve

The first start prints a pairing code and a QR code, and writes a settings
file (`hudhud.toml`) in your data folder. Set `vault_path` there to your
Obsidian vault and restart. Open the printed address on your PC or phone (same
network, or over Tailscale), enter the code, and import a book.

Pair another device with `uv run --project hub hudhud pair`.

## Layout

    hub/         Python hub (uv project): FastAPI, SQLite, vault writer
    client/      browser reader (React, Vite, foliate-js)
    LICENSE      AGPL-3.0-or-later
    CLA.md       contributor licence agreement

## Development

    uv run --project hub pytest hub/tests
    uv run --project hub ruff check .
    pnpm --dir client test
    pnpm --dir client typecheck
    pnpm --dir client dev      # hot-reloading client against a running hub

## Licence

AGPL-3.0-or-later. Outside contributions need the [CLA](CLA.md).
