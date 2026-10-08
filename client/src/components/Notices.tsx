// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from 'react'

import { type Notice, onNotice } from '../lib/notices'
import { Icon } from './Icon'

export function Notices() {
  const [notices, setNotices] = useState<Notice[]>([])

  useEffect(() => onNotice((notice) => {
    setNotices((list) => [...list.slice(-2), notice])
    setTimeout(() => setNotices((list) => list.filter((n) => n.id !== notice.id)), 8000)
  }), [])

  if (!notices.length) return null
  return (
    <div className="fixed inset-x-0 bottom-[calc(4rem+var(--safe-bottom))] z-[60] mx-auto flex w-full max-w-md flex-col gap-2 px-4"
         role="status" aria-live="polite">
      {notices.map((n) => (
        <div key={n.id}
             className="flex items-start gap-3 rounded-xl border border-rule bg-raised px-4 py-3 text-sm text-ink shadow-lg">
          <p className="flex-1">{n.message}</p>
          <button type="button" aria-label="Dismiss"
                  onClick={() => setNotices((list) => list.filter((x) => x.id !== n.id))}>
            <Icon name="close" size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}
