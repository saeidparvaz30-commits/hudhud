// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { drawableLocator, navigationTarget, sectionCfi, sectionIndex, storedLocator,
         TEXT_PREFIX } from './locators'

describe('locators across PDF views', () => {
  it('reads the page from page-view and text-view CFIs', () => {
    expect(sectionIndex('epubcfi(/6/14!/4/2/1:0)')).toBe(6)
    expect(sectionIndex(`${TEXT_PREFIX}epubcfi(/6/2!/4/2,/1:0,/1:9)`)).toBe(0)
    expect(sectionIndex('not a cfi')).toBeNull()
  })

  it('round-trips a page through a section-level CFI', () => {
    expect(sectionIndex(sectionCfi(41))).toBe(41)
  })

  it('draws a highlight only in the view it was made in', () => {
    const page = 'epubcfi(/6/4!/4/2,/1:0,/1:5)'
    const text = storedLocator('epubcfi(/6/4!/4/6,/1:0,/1:5)', true)
    expect(drawableLocator(page, false)).toBe(page)
    expect(drawableLocator(page, true)).toBeNull()
    expect(drawableLocator(text, true)).toBe('epubcfi(/6/4!/4/6,/1:0,/1:5)')
    expect(drawableLocator(text, false)).toBeNull()
  })

  it('jumps to the right page when a highlight comes from the other view', () => {
    const text = storedLocator('epubcfi(/6/10!/4/6,/1:0,/1:5)', true)
    expect(navigationTarget(text, false)).toBe(4)
    expect(navigationTarget('epubcfi(/6/10!/4/2,/1:0,/1:5)', true)).toBe(4)
    expect(navigationTarget(text, true)).toBe('epubcfi(/6/10!/4/6,/1:0,/1:5)')
  })
})
