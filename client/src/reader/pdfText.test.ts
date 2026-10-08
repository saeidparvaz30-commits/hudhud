// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { findFigureBands, pagesToFb2, type TextItem, textItemsToBlocks } from './pdfText'

/** A text run at (x, y) in PDF space (y grows upwards), 10pt unless given. */
const run = (str: string, x: number, y: number, size = 10, width = str.length * 5): TextItem =>
  ({ str, transform: [size, 0, 0, size, x, y], width, height: size, hasEOL: false })

describe('textItemsToBlocks', () => {
  it('joins the lines of a paragraph and splits on a larger gap', () => {
    const blocks = textItemsToBlocks([
      run('The confidence people have in', 72, 700),
      run('their intuitions is not reliable.', 72, 688),
      run('A second paragraph starts', 72, 664),
      run('after a bigger gap.', 72, 652),
    ])
    expect(blocks.map(({ text, heading }) => ({ text, heading }))).toEqual([
      { text: 'The confidence people have in their intuitions is not reliable.', heading: false },
      { text: 'A second paragraph starts after a bigger gap.', heading: false },
    ])
    expect(blocks[0].top).toBe(710)  // y of the first line's top, in PDF units
  })

  it('rejoins words hyphenated across lines', () => {
    const blocks = textItemsToBlocks([run('a well-known exam-', 72, 700), run('ple of this', 72, 688)])
    expect(blocks[0].text).toBe('a well-known example of this')
  })

  it('keeps runs on one line together, with spaces where there are gaps', () => {
    const blocks = textItemsToBlocks([run('Hello', 72, 700, 10, 25), run('world', 110, 700)])
    expect(blocks[0].text).toBe('Hello world')
  })

  it('marks large text as a heading', () => {
    const blocks = textItemsToBlocks([
      run('Chapter 1', 72, 740, 18),
      run('Body text here', 72, 700),
      run('and more body.', 72, 688),
    ])
    expect(blocks[0]).toMatchObject({ text: 'Chapter 1', heading: true })
    expect(blocks[1].heading).toBe(false)
  })

  it('starts a paragraph at an indented line', () => {
    const blocks = textItemsToBlocks([
      run('End of one paragraph.', 72, 700),
      run('Indented start of the next.', 90, 688),
      run('continues here.', 72, 676),
    ])
    expect(blocks.map((b) => b.text)).toEqual([
      'End of one paragraph.', 'Indented start of the next. continues here.'])
  })

  it('drops bare page numbers', () => {
    const blocks = textItemsToBlocks([run('Some text', 72, 700), run('42', 300, 40)])
    expect(blocks.map((b) => b.text)).toEqual(['Some text'])
  })

  it('returns nothing for an image-only page', () => {
    expect(textItemsToBlocks([])).toEqual([])
    expect(textItemsToBlocks([run('   ', 72, 700)])).toEqual([])
  })
})

describe('findFigureBands', () => {
  const W = 600
  const H = 800
  /** Ink per row: `ranges` of [from, to) rows with `count` drawn pixels each. */
  const ink = (...ranges: [number, number, number][]) => {
    const rows = new Uint32Array(H)
    for (const [from, to, count] of ranges) rows.fill(count, from, to)
    return rows
  }

  it('finds a drawing between paragraphs', () => {
    const bands = findFigureBands(ink([300, 500, 120]), [], W, H)
    expect(bands).toHaveLength(1)
    expect(bands[0].y0).toBeLessThanOrEqual(300)
    expect(bands[0].y1).toBeGreaterThanOrEqual(500)
  })

  it('keeps a figure whole across small gaps in its ink', () => {
    expect(findFigureBands(ink([300, 380, 80], [390, 500, 80]), [], W, H)).toHaveLength(1)
  })

  it('keeps two rows of boxes joined by a thin arrow as one figure', () => {
    // row of boxes, a 2-px arrow, a gap, another row: one diagram
    const rows = ink([390, 450, 300], [450, 480, 2], [500, 630, 200])
    const bands = findFigureBands(rows, [], W, H)
    expect(bands).toHaveLength(1)
    expect(bands[0].y0).toBeLessThanOrEqual(390)
    expect(bands[0].y1).toBeGreaterThanOrEqual(630)
  })

  it('ignores thin rules and specks', () => {
    expect(findFigureBands(ink([300, 303, 400], [600, 610, 2]), [], W, H)).toEqual([])
  })

  it('leaves a boxed sidebar full of text as text', () => {
    const lines = Array.from({ length: 12 }, (_, i) =>
      ({ x0: 60, x1: 540, y0: 210 + i * 24, y1: 226 + i * 24 }))
    // the box border: two horizontal rules and two vertical sides
    const box = ink([200, 202, 500], [202, 498, 4], [498, 500, 500])
    expect(findFigureBands(box, lines, W, H)).toEqual([])
  })

  it('keeps a diagram with a few labels as a figure', () => {
    const labels = [{ x0: 100, x1: 220, y0: 340, y1: 356 }, { x0: 380, x1: 470, y0: 420, y1: 436 }]
    expect(findFigureBands(ink([300, 500, 150]), labels, W, H)).toHaveLength(1)
  })
})

describe('pagesToFb2', () => {
  it('embeds figures as images in reading order', () => {
    const fb2 = pagesToFb2([[
      { text: 'Before the figure.', heading: false, top: 700 },
      { image: 'QUJD', type: 'image/jpeg', top: 500 },
      { text: 'Figure 1-13. A caption.', heading: false, top: 300 },
    ]], 'Book', 'en')
    expect(fb2).toContain('xmlns:l="http://www.w3.org/1999/xlink"')
    expect(fb2).toMatch(/<p>Before the figure\.<\/p><image l:href="#fig-0-0"\/><p>Figure 1-13/)
    expect(fb2).toContain('<binary id="fig-0-0" content-type="image/jpeg">QUJD</binary>')
  })

  it('makes one section per page so page N is section N in both views', () => {
    const fb2 = pagesToFb2([[{ text: 'Intro', heading: true }, { text: 'a < b', heading: false }], []],
                           'My <PDF>', 'en')
    expect(fb2.match(/<section>/g)).toHaveLength(2)
    expect(fb2).toContain('<subtitle>Intro</subtitle><p>a &lt; b</p>')
    expect(fb2).toContain('<book-title>My &lt;PDF&gt;</book-title>')
    expect(fb2).toContain('This page has no text')
  })
})
