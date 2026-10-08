// SPDX-License-Identifier: AGPL-3.0-or-later
import { type FormEvent, useEffect, useState } from 'react'

import { health, normalizeHubUrl, pair } from '../lib/api'
import { resetSyncedData, setPairing } from '../lib/db'
import { navigate } from '../lib/hooks'
import { notifyData, syncNow } from '../lib/sync'

function guessDeviceName(): string {
  const ua = navigator.userAgent
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/iPad/.test(ua)) return 'iPad'
  if (/Android/.test(ua)) return /Mobile/.test(ua) ? 'Android phone' : 'Android tablet'
  if (/Windows/.test(ua)) return 'Windows PC'
  if (/Mac/.test(ua)) return 'Mac'
  return 'Browser'
}

export function PairScreen() {
  const params = new URLSearchParams(window.location.search)
  const [hubUrl, setHubUrl] = useState('http://localhost:8765')
  const [code, setCode] = useState(params.get('pair') ?? '')
  const [name, setName] = useState(guessDeviceName())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // When the hub itself serves this page, its address is simply our origin.
    void health(window.location.origin).then(() => setHubUrl(window.location.origin),
                                             () => undefined)
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const url = normalizeHubUrl(hubUrl)
      const { device_id, token } = await pair(url, code, name.trim() || guessDeviceName())
      // A new pairing may be a different or rebuilt hub: rebuild synced data from zero.
      await resetSyncedData()
      await setPairing({ hubUrl: url, token, deviceId: device_id, deviceName: name.trim() })
      navigate('/', true)
      notifyData()
      void syncNow()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const field = 'w-full rounded-lg border border-rule bg-raised px-3 py-2.5 text-ink outline-none focus:border-accent'

  return (
    <main className="paper-grain grid min-h-full place-items-center px-4 py-10">
      <form onSubmit={submit}
            className="relative z-10 w-full max-w-sm rounded-2xl border border-rule bg-raised/80 p-7 shadow-sm">
        <img src="/hudhud.svg" alt="" className="mb-4 h-12 w-12" />
        <h1 className="font-serif text-3xl">Hudhud</h1>
        <p className="mt-2 text-sm text-muted">
          Pair this device with your hub. Run <code className="rounded bg-ink/10 px-1">hudhud pair</code> on
          the hub computer to get a code.
        </p>
        <label className="mt-6 block text-sm font-medium" htmlFor="hub">Hub address</label>
        <input id="hub" className={`${field} mt-1`} value={hubUrl} inputMode="url"
               autoCapitalize="off" autoCorrect="off" onChange={(e) => setHubUrl(e.target.value)} />
        <label className="mt-4 block text-sm font-medium" htmlFor="code">Pairing code</label>
        <input id="code" className={`${field} mt-1 font-mono tracking-widest uppercase`} value={code}
               placeholder="ABCD-EFGH" autoCapitalize="characters" autoComplete="one-time-code"
               onChange={(e) => setCode(e.target.value)} required />
        <label className="mt-4 block text-sm font-medium" htmlFor="name">This device</label>
        <input id="name" className={`${field} mt-1`} value={name}
               onChange={(e) => setName(e.target.value)} />
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
        <button type="submit" disabled={busy}
                className="mt-6 w-full rounded-lg bg-accent px-4 py-2.5 font-medium text-paper disabled:opacity-60">
          {busy ? 'Pairing…' : 'Pair device'}
        </button>
      </form>
    </main>
  )
}
