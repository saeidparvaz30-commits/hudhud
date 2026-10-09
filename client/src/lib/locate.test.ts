// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { findHub, firstReachable, scanTargets } from './locate'

describe('scanTargets', () => {
  it('lists the rest of each private /24 on the same port', () => {
    const targets = scanTargets(['http://192.168.1.5:8765'])
    expect(targets).toHaveLength(253)
    expect(targets).toContain('http://192.168.1.6:8765')
    expect(targets).not.toContain('http://192.168.1.5:8765')
    expect(targets).not.toContain('http://192.168.1.0:8765')
    expect(targets).not.toContain('http://192.168.1.255:8765')
  })

  it('never scans public addresses or names', () => {
    expect(scanTargets(['https://pc.ts.net', 'http://100.64.0.2:8765', 'http://8.8.8.8:8765']))
      .toEqual([])
  })
})

describe('findHub', () => {
  const pairing = { hubUrl: 'http://192.168.1.5:8765', hubId: 'h1',
                    hubUrls: ['http://192.168.1.5:8765', 'https://pc.ts.net'] }

  it('tries the other known addresses before scanning', async () => {
    const probed: string[] = []
    const found = await findHub(pairing, { scan: true, probe: async (url) => {
      probed.push(url)
      return url === 'https://pc.ts.net' ? 'h1' : null
    } })
    expect(found).toBe('https://pc.ts.net')
    expect(probed).toEqual(['https://pc.ts.net'])
  })

  it('scans the old subnet for the same hub when its address changed', async () => {
    const found = await findHub(pairing, { scan: true,
      probe: async (url) => (url === 'http://192.168.1.77:8765' ? 'h1' : null) })
    expect(found).toBe('http://192.168.1.77:8765')
  })

  it('ignores a different hub, and does not scan unless asked', async () => {
    const other = async () => 'someone-else'
    expect(await findHub(pairing, { scan: true, probe: other })).toBeNull()
    let probes = 0
    await findHub(pairing, { scan: false, probe: async () => { probes++; return null } })
    expect(probes).toBe(1)
  })
})

describe('firstReachable', () => {
  it('pairs at the first listed address that answers, with its hub id', async () => {
    const probe = async (url: string) => (url === 'http://192.168.1.5:8765' ? 'h1' : null)
    expect(await firstReachable(['https://pc.ts.net', 'http://192.168.1.5:8765'], probe))
      .toEqual({ hubUrl: 'http://192.168.1.5:8765', hubId: 'h1' })
    expect(await firstReachable(['https://pc.ts.net'], probe)).toBeNull()
  })
})
