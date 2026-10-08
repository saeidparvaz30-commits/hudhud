// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from 'react'

import { type Device, health, listDevices, revokeDevice } from '../lib/api'
import { clearAll, getPairing } from '../lib/db'
import { navigate, setPrefs, type Theme, useLive, usePrefs } from '../lib/hooks'
import { IconButton } from './Icon'

const SOURCE = 'https://github.com/saeidparvaz30-commits/hudhud'

export function Settings() {
  const pairing = useLive(getPairing, [])
  const prefs = usePrefs()
  const [devices, setDevices] = useState<Device[]>([])
  const [status, setStatus] = useState<string>('Checking…')
  const [version, setVersion] = useState('')

  useEffect(() => {
    if (!pairing) return
    void health(pairing.hubUrl).then((h) => {
      setVersion(h.version)
      setStatus(!h.vault_enabled ? 'Connected. No Obsidian vault configured on the hub.'
        : h.vault_ok ? 'Connected. Highlights are written to your vault.'
          : 'Connected, but the hub cannot write to the vault.')
    }, () => setStatus('The hub is unreachable.'))
    void listDevices(pairing).then(setDevices, () => undefined)
  }, [pairing])

  async function revoke(device: Device) {
    if (!pairing) return
    await revokeDevice(pairing, device.id)
    setDevices(await listDevices(pairing))
  }

  async function unpair() {
    if (pairing) await revokeDevice(pairing, pairing.deviceId).catch(() => undefined)
    await clearAll()
    navigate('/', true)
    window.location.reload()
  }

  const section = 'relative z-10 mt-6 rounded-xl border border-rule bg-raised/70 p-5'

  return (
    <div className="paper-grain min-h-full">
      <header className="relative z-10 mx-auto flex max-w-2xl items-center gap-2 px-4 pt-6">
        <IconButton icon="back" label="Back to library" onClick={() => navigate('/')} />
        <h1 className="font-serif text-2xl">Settings</h1>
      </header>
      <main className="mx-auto max-w-2xl px-4 pb-16">
        <section className={section}>
          <h2 className="font-medium">Appearance</h2>
          <div className="mt-3 flex gap-3">
            {(['paper', 'sepia', 'night'] as Theme[]).map((theme) => (
              <button key={theme} type="button" onClick={() => setPrefs({ theme })} data-theme={theme}
                      className={`h-14 flex-1 rounded-lg border-2 bg-paper text-sm capitalize text-ink ${prefs.theme === theme ? 'border-accent' : 'border-rule'}`}>
                {theme}
              </button>
            ))}
          </div>
        </section>

        <section className={section}>
          <h2 className="font-medium">Hub</h2>
          <p className="mt-2 text-sm break-all">{pairing?.hubUrl}</p>
          <p className="mt-1 text-sm text-muted">{status}</p>
          <h3 className="mt-5 text-sm font-medium">Paired devices</h3>
          <ul className="mt-2 divide-y divide-rule">
            {devices.map((d) => (
              <li key={d.id} className="flex items-center justify-between py-2 text-sm">
                <span>
                  {d.name} {d.current && <span className="text-muted">(this device)</span>}
                  <span className="block text-xs text-muted">last seen {new Date(d.last_seen).toLocaleString()}</span>
                </span>
                {!d.current && (
                  <button type="button" onClick={() => void revoke(d)}
                          className="rounded-md px-3 py-1 text-red-700 hover:bg-ink/5">Revoke</button>
                )}
              </li>
            ))}
          </ul>
          <button type="button" onClick={() => void unpair()}
                  className="mt-4 rounded-lg border border-red-300 px-4 py-2 text-sm text-red-700 hover:bg-red-50">
            Unpair this device
          </button>
        </section>

        <section className={section}>
          <h2 className="font-medium">About</h2>
          <p className="mt-2 text-sm text-muted">
            Hudhud {version} is free software under the GNU Affero General Public License v3 or later.
            {' '}<a className="text-accent underline" href={SOURCE} target="_blank" rel="noreferrer">Source code</a>
          </p>
        </section>
      </main>
    </div>
  )
}
