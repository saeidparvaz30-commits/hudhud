// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * A PDF has two views: pages (foliate's PDF renderer) and text (the same PDF
 * rebuilt as FB2, one section per page). Both number their sections by page, and
 * foliate gives section-only CFIs the same form in both (`epubcfi(/6/2N+2)`), so a
 * reading position moves between views at page granularity.
 *
 * Highlights are precise CFIs into one view's DOM, so text-view highlights carry a
 * prefix and are only drawn in the view they were made in.
 */
export const TEXT_PREFIX = 'hudhud-text:'

/** The section (page) a CFI points into, or null if it is not a CFI. */
export function sectionIndex(locator: string): number | null {
  const match = locator.replace(TEXT_PREFIX, '').match(/^epubcfi\(\/6\/(\d+)/)
  return match ? Number(match[1]) / 2 - 1 : null
}

/** A section-level CFI that resolves in either view. */
export function sectionCfi(index: number): string {
  return `epubcfi(/6/${(index + 1) * 2})`
}

/** The locator to store for a selection made in the current view. */
export function storedLocator(cfi: string, textView: boolean): string {
  return textView ? TEXT_PREFIX + cfi : cfi
}

/** The CFI to draw in the current view, or null if the highlight belongs to the other one. */
export function drawableLocator(locator: string, textView: boolean): string | null {
  const isText = locator.startsWith(TEXT_PREFIX)
  if (isText !== textView) return null
  return isText ? locator.slice(TEXT_PREFIX.length) : locator
}

/** Where to go for a stored locator: exact in its own view, its page in the other. */
export function navigationTarget(locator: string, textView: boolean): string | number {
  const drawable = drawableLocator(locator, textView)
  if (drawable) return drawable
  return sectionIndex(locator) ?? 0
}
