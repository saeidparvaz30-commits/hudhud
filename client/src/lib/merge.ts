// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Highlight, Progress } from './types'

/** Last-write-wins on (updated_at, device_id), the same rule the hub applies. */
export function newer(a: { updated_at: string; device_id: string },
                      b: { updated_at: string; device_id: string }): boolean {
  if (a.updated_at !== b.updated_at) return a.updated_at > b.updated_at
  return a.device_id > b.device_id
}

/** The highlight to keep when a remote copy arrives. Tombstones are final. */
export function mergeHighlight(local: Highlight | undefined, remote: Highlight): Highlight {
  if (!local) return remote
  if (local.deleted) return local
  if (remote.deleted) return remote
  return newer(remote, local) ? remote : local
}

/**
 * Offer "Continue from <device>?" only when another device is newer than this one
 * and more than one page away (spec section 8).
 */
export function shouldOfferResume(own: Progress | undefined, other: Progress | undefined,
                                  totalPages: number): boolean {
  if (!other) return false
  if (own && other.updated_at <= own.updated_at) return false
  const pages = Math.max(1, totalPages)
  return Math.abs(other.fraction - (own?.fraction ?? 0)) > 1 / pages
}
