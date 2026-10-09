// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Pairing } from './types'

/** Asks an address which hub answers there: its hub id, or null if none does. */
export type Probe = (url: string) => Promise<string | null>

const PROBE_TIMEOUT = 1_500
const SCAN_CONCURRENCY = 32
const PRIVATE_V4 = /^(10\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+|192\.168\.\d+)\.(\d+)$/

export const probeHub: Probe = async (url) => {
  try {
    const response = await fetch(`${url}/health`, { signal: AbortSignal.timeout(PROBE_TIMEOUT) })
    if (!response.ok) return null
    const body = await response.json()
    return typeof body.hub_id === 'string' ? body.hub_id : null
  } catch {
    return null
  }
}

/** The other hosts of each private /24 the hub was known at, on the same port. */
export function scanTargets(urls: string[]): string[] {
  const known = new Set(urls)
  const targets: string[] = []
  for (const raw of urls) {
    let url: URL
    try {
      url = new URL(raw)
    } catch {
      continue
    }
    const match = url.protocol === 'http:' && PRIVATE_V4.exec(url.hostname)
    if (!match) continue
    for (let host = 1; host <= 254; host++) {
      const target = `http://${match[1]}.${host}${url.port ? `:${url.port}` : ''}`
      if (!known.has(target)) {
        known.add(target)
        targets.push(target)
      }
    }
  }
  return targets
}

/**
 * Where this device's hub answers now, or null. Known addresses first, then (if `scan`)
 * the old LAN subnets. A hub only counts when its id matches, so the token never goes
 * to some other machine.
 */
export async function findHub(
  pairing: Pick<Pairing, 'hubUrl' | 'hubId' | 'hubUrls'>,
  { scan, probe = probeHub }: { scan: boolean; probe?: Probe },
): Promise<string | null> {
  const known = (pairing.hubUrls ?? []).filter((url) => url !== pairing.hubUrl)
  const isOurs = (id: string | null) => id !== null && (!pairing.hubId || id === pairing.hubId)
  for (const url of known) {
    if (isOurs(await probe(url))) return url
  }
  // Without an id there is nothing to recognise the hub by on a strange address.
  if (!scan || !pairing.hubId) return null
  const queue = scanTargets([pairing.hubUrl, ...known])
  let found: string | null = null
  const worker = async () => {
    while (!found && queue.length) {
      const url = queue.shift()!
      if (isOurs(await probe(url))) found = url
    }
  }
  await Promise.all(Array.from({ length: SCAN_CONCURRENCY }, worker))
  return found
}

/** The first of `urls` where a hub answers, in order, with that hub's id. */
export async function firstReachable(
  urls: string[], probe: Probe = probeHub,
): Promise<{ hubUrl: string; hubId: string } | null> {
  for (const url of urls) {
    const hubId = await probe(url)
    if (hubId) return { hubUrl: url, hubId }
  }
  return null
}
