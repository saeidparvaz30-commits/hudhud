// SPDX-License-Identifier: AGPL-3.0-or-later
/** Short messages for the person using the app (refused changes, failed saves). */
export interface Notice { id: number; message: string }

const listeners = new Set<(notice: Notice) => void>()
let next = 1

export function notify(message: string): void {
  const notice = { id: next++, message }
  for (const listener of listeners) listener(notice)
}

export function onNotice(listener: (notice: Notice) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
