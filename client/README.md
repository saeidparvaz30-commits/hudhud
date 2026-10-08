# Hudhud client

The reader: React + TypeScript + Vite + Tailwind. Books render through the
vendored [foliate-js](public/foliate-js/VENDORED.md) (MIT), which includes
PDF.js for PDFs.

    pnpm install
    pnpm dev        # http://localhost:5173, talks to a hub on :8765 (CORS is open)
    pnpm test       # vitest
    pnpm typecheck
    pnpm lint
    pnpm build      # dist/, served by `hudhud serve`

The client never assumes the hub serves it: the hub address comes from pairing.
