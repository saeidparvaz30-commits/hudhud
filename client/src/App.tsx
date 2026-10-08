// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect } from 'react'

import { Library } from './components/Library'
import { Notices } from './components/Notices'
import { PairScreen } from './components/PairScreen'
import { Settings } from './components/Settings'
import { getPairing } from './lib/db'
import { useLive, usePrefs, useRoute, useSyncState } from './lib/hooks'
import { startAutoSync } from './lib/sync'
import { Reader } from './reader/Reader'

export default function App() {
  usePrefs()  // applies the theme to <html>
  // undefined while IndexedDB loads, null when this device has never paired.
  const pairing = useLive(async () => (await getPairing()) ?? null, [])
  const sync = useSyncState()
  const route = useRoute()
  const paired = Boolean(pairing) && sync !== 'unpaired'

  useEffect(() => (paired ? startAutoSync() : undefined), [paired])

  if (pairing === undefined) return null
  return (
    <>
      <Screen paired={paired} route={route} />
      <Notices />
    </>
  )
}

function Screen({ paired, route }: { paired: boolean; route: ReturnType<typeof useRoute> }) {
  if (!paired) return <PairScreen />
  if (route.name === 'reader') {
    return <Reader key={route.bookId} bookId={route.bookId} highlightId={route.highlight} />
  }
  if (route.name === 'settings') return <Settings />
  return <Library />
}
