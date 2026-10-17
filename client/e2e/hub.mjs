// Starts a throwaway hub for the end-to-end tests: fresh data dir and vault, the
// download-free test embedder, serving the built client from client/dist.
import { spawn } from 'node:child_process'
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { DATA_DIR, PORT, VAULT_DIR, hudhud } from './paths.mjs'

rmSync(DATA_DIR, { recursive: true, force: true })
rmSync(VAULT_DIR, { recursive: true, force: true })
mkdirSync(DATA_DIR, { recursive: true })
mkdirSync(VAULT_DIR, { recursive: true })
writeFileSync(`${DATA_DIR}/hudhud.toml`, [
  `vault_path = ${JSON.stringify(VAULT_DIR)}`,
  `host = "127.0.0.1"`,
  `port = ${PORT}`,
  `embed_model = "hash"`,
  '',
].join('\n'))

const [cmd, args] = hudhud(['serve', '--no-browser'])
const hub = spawn(cmd, args, { stdio: 'inherit' })
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => hub.kill())
hub.on('exit', (code) => process.exit(code ?? 0))
