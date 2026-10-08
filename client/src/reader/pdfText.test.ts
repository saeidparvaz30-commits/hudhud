// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { pagesToFb2, type TextItem, textItemsToBlocks } from './pdfText'

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
    expect(blocks).toEqual([
      { text: 'The confidence people have in their intuitions is not reliable.', heading: false },
      { text: 'A second paragraph starts after a bigger gap.', heading: false },
    ])
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
    expect(blocks[0]).toEqual({ text: 'Chapter 1', heading: true })
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

describe('pagesToFb2', () => {
  it('makes one section per page so page N is section N in both views', () => {
    const fb2 = pagesToFb2([[{ text: 'Intro', heading: true }, { text: 'a < b', heading: false }], []],
                           'My <PDF>', 'en')
    expect(fb2.match(/<section>/g)).toHaveLength(2)
    expect(fb2).toContain('<subtitle>Intro</subtitle><p>a &lt; b</p>')
    expect(fb2).toContain('<book-title>My &lt;PDF&gt;</book-title>')
    expect(fb2).toContain('This page has no text')
  })
})
