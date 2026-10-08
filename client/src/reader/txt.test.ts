// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'

import { guessLanguage, txtToFb2 } from './txt'

describe('txtToFb2', () => {
  it('splits paragraphs on blank lines and escapes XML', () => {
    const fb2 = txtToFb2('First <line>\nwraps here.\r\n\r\nSecond & last.', 'A & B')
    expect(fb2).toContain('<p>First &lt;line&gt; wraps here.</p><p>Second &amp; last.</p>')
    expect(fb2).toContain('<book-title>A &amp; B</book-title>')
    expect(new DOMParserShim(fb2).ok).toBe(true)
  })

  it('chunks long texts into sections', () => {
    const text = Array.from({ length: 95 }, (_, i) => `Paragraph ${i}`).join('\n\n')
    expect(txtToFb2(text, 't').match(/<section>/g)).toHaveLength(3)
  })

  it('marks Farsi text so pages run right to left', () => {
    expect(guessLanguage('یک روز، روزگاری در شهری دور')).toBe('fa')
    expect(guessLanguage('Once upon a time')).toBe('en')
    expect(txtToFb2('سلام دنیا', 'عنوان')).toContain('<lang>fa</lang>')
    expect(txtToFb2('hello', 't', 'de')).toContain('<lang>de</lang>')
  })

  it('drops control characters XML forbids', () => {
    expect(txtToFb2('bell\u0007 here', 't')).toContain('<p>bell here</p>')
  })
})

/** Minimal well-formedness check without a DOM: every opened tag closes in order. */
class DOMParserShim {
  ok: boolean
  constructor(xml: string) {
    const stack: string[] = []
    let ok = true
    for (const [, close, name, selfClose] of xml.replace(/<\?xml[^>]*\?>/, '')
      .matchAll(/<(\/?)([\w-]+)[^>]*?(\/?)>/g)) {
      if (selfClose) continue
      if (close) ok &&= stack.pop() === name
      else stack.push(name)
    }
    this.ok = ok && stack.length === 0
  }
}
