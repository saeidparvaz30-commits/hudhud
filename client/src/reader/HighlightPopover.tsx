// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useRef, useState } from 'react'

import { Icon } from '../components/Icon'
import type { Highlight, HighlightColor } from '../lib/types'
import { HIGHLIGHT_CSS } from './foliate'

const COLORS: HighlightColor[] = ['yellow', 'green', 'blue', 'pink', 'purple']

export interface PopoverTarget {
  x: number
  top: number
  bottom: number
  /** A new selection... */
  cfi?: string
  text?: string
  /** ...or an existing highlight. */
  existing?: Highlight
}

interface Props {
  target: PopoverTarget
  onCreate(color: HighlightColor, comment: string): void
  onUpdate(highlight: Highlight, patch: { color?: HighlightColor; comment?: string }): void
  onDelete(highlight: Highlight): void
  onClose(): void
}

export function HighlightPopover({ target, onCreate, onUpdate, onDelete, onClose }: Props) {
  const { existing } = target
  const [noting, setNoting] = useState(Boolean(existing))
  const [comment, setComment] = useState(existing?.comment ?? '')
  const box = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: target.x, top: target.bottom + 10 })

  useEffect(() => {
    const el = box.current
    if (!el) return
    const { width, height } = el.getBoundingClientRect()
    const left = Math.min(Math.max(8, target.x - width / 2), window.innerWidth - width - 8)
    const below = target.bottom + 10
    const top = below + height < window.innerHeight - 8 ? below
      : Math.max(8, target.top - height - 10)
    setPos({ left, top })
  }, [target, noting])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function pick(color: HighlightColor) {
    if (existing) onUpdate(existing, { color })
    else if (!noting) onCreate(color, '')
    else onCreate(color, comment)
  }

  function saveNote() {
    if (existing) onUpdate(existing, { comment })
    else onCreate('yellow', comment)
  }

  return (
    <>
      <div className="fixed inset-0 z-40" onPointerDown={onClose} />
      <div ref={box} role="dialog" aria-label={existing ? 'Edit highlight' : 'Highlight selection'}
           style={{ left: pos.left, top: pos.top }}
           className="fixed z-50 w-72 rounded-xl border border-rule bg-raised p-2.5 text-ink shadow-xl">
        <div className="flex items-center gap-1.5">
          {COLORS.map((color) => (
            <button key={color} type="button" aria-label={`${color} highlight`} onClick={() => pick(color)}
                    className={`h-8 w-8 rounded-full border-2 ${existing?.color === color ? 'border-ink' : 'border-transparent'}`}
                    style={{ background: HIGHLIGHT_CSS[color] }} />
          ))}
          <span className="mx-1 h-6 w-px bg-rule" />
          <button type="button" aria-label="Add a note" onClick={() => setNoting(true)}
                  className="grid h-8 w-8 place-items-center rounded-full hover:bg-ink/10">
            <Icon name="note" size={18} />
          </button>
          {existing && (
            <button type="button" aria-label="Delete highlight" onClick={() => onDelete(existing)}
                    className="grid h-8 w-8 place-items-center rounded-full text-red-700 hover:bg-ink/10">
              <Icon name="trash" size={18} />
            </button>
          )}
        </div>
        {noting && (
          <div className="mt-2">
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} dir="auto"
                      autoFocus placeholder="Your note"
                      className="w-full resize-none rounded-lg border border-rule bg-paper p-2 text-sm outline-none focus:border-accent" />
            <div className="mt-1 flex justify-end gap-2">
              <button type="button" onClick={onClose} className="rounded-md px-3 py-1 text-sm hover:bg-ink/5">
                Cancel
              </button>
              <button type="button" onClick={saveNote}
                      className="rounded-md bg-accent px-3 py-1 text-sm text-paper">Save</button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
