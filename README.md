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

## Install

**Windows:** run `Hudhud_<version>_x64-setup.exe`. Hudhud starts its hub and
opens the reader, already paired. Closing the window keeps it in the tray so
your phone can still sync; *Quit* in the tray menu stops it. Turn on *Start with
Windows* in the same menu.

**Android:** install `hudhud.apk`, then on the PC open Settings > *Add a device*
and tap *Scan QR code* in the app.

**Any browser:** open the hub's address on the device and pair it the same way.

Settings live in `hudhud.toml` in the data folder (`%LOCALAPPDATA%\hudhud` on
Windows). Set `vault_path` to your Obsidian vault, and `public_url` to the
address your phone uses (for example a Tailscale name).

## Build from source

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with
pnpm; Rust for the desktop app; JDK 21 and the Android SDK for the Android app.

    pnpm --dir client install && pnpm --dir client build
    uv run --project hub hudhud serve          # the hub, from source

    # Windows app (hub packaged inside)
    pnpm --dir desktop install
    pnpm --dir desktop sidecar                 # packages the hub as hudhud.exe
    pnpm --dir desktop build                   # installer in desktop/src-tauri/target/release/bundle/nsis

    # Android app
    pnpm --dir client exec cap sync android
    cd client/android && ./gradlew assembleDebug

## Layout

    hub/         Python hub (uv project): FastAPI, SQLite, vault writer
    client/      the reader (React, Vite, foliate-js); client/android is the Android app
    desktop/     the Windows app (Tauri) that runs the hub and shows the reader
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
