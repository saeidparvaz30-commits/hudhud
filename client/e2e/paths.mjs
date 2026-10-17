import { fileURLToPath } from 'node:url'

const here = (p) => fileURLToPath(new URL(p, import.meta.url))

export const PORT = 8799
export const HUB_URL = `http://127.0.0.1:${PORT}`
export const DATA_DIR = here('./.data/hub')
export const VAULT_DIR = here('./.data/vault')

/** The command line for the hub CLI against the test data dir. */
export function hudhud(args) {
  return ['uv', ['run', '--project', here('../../hub'), 'hudhud', '--data-dir', DATA_DIR, ...args]]
}
