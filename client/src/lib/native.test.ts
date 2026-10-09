// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { parsePairingLink } from './native'

describe('parsePairingLink', () => {
  it('splits an invite link into hub and code', () => {
    expect(parsePairingLink('https://reader.example-tailnet.ts.net/?pair=CARWW1GT'))
      .toEqual({ hubUrl: 'https://reader.example-tailnet.ts.net', code: 'CARWW1GT',
                 hubUrls: ['https://reader.example-tailnet.ts.net'] })
    expect(parsePairingLink(' http://192.168.1.20:8765/?pair=ABCD1234 \n'))
      .toEqual({ hubUrl: 'http://192.168.1.20:8765', code: 'ABCD1234',
                 hubUrls: ['http://192.168.1.20:8765'] })
  })

  it('collects every other address the hub listed', () => {
    const link = 'https://pc.ts.net/?pair=ABCD1234&hub=http%3A%2F%2F192.168.1.5%3A8765'
      + '&hub=javascript%3Aalert(1)&hub=http%3A%2F%2F10.0.0.7%3A8765%2F'
    expect(parsePairingLink(link)?.hubUrls)
      .toEqual(['https://pc.ts.net', 'http://192.168.1.5:8765', 'http://10.0.0.7:8765'])
  })

  it('rejects anything that is not an invite', () => {
    expect(parsePairingLink('https://example.com/')).toBeNull()
    expect(parsePairingLink('ABCD1234')).toBeNull()
    expect(parsePairingLink('javascript:alert(1)?pair=x')).toBeNull()
  })
})
