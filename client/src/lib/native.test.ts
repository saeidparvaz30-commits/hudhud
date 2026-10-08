// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { parsePairingLink } from './native'

describe('parsePairingLink', () => {
  it('splits an invite link into hub and code', () => {
    expect(parsePairingLink('https://monsterdev.tailfceb4e.ts.net/?pair=CARWW1GT'))
      .toEqual({ hubUrl: 'https://monsterdev.tailfceb4e.ts.net', code: 'CARWW1GT' })
    expect(parsePairingLink(' http://192.168.1.20:8765/?pair=ABCD1234 \n'))
      .toEqual({ hubUrl: 'http://192.168.1.20:8765', code: 'ABCD1234' })
  })

  it('rejects anything that is not an invite', () => {
    expect(parsePairingLink('https://example.com/')).toBeNull()
    expect(parsePairingLink('ABCD1234')).toBeNull()
    expect(parsePairingLink('javascript:alert(1)?pair=x')).toBeNull()
  })
})
