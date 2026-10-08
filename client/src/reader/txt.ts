// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * foliate-js has no plain-text reader, but it reads FB2. A TXT book becomes a
 * minimal FB2 document: paragraphs split on blank lines, chapters every ~40
 * paragraphs so the paginator never lays out one enormous section.
 */

const RTL_SCRIPT = /[֐-ࣿיִ-﷿ﹰ-﻿]/g
const PARAGRAPHS_PER_SECTION = 40

export function escapeXml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Characters XML 1.0 forbids (control codes other than tab, LF, CR).
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
}

/** 'fa' when most letters are Arabic/Hebrew script, else 'en'. Drives page direction. */
export function guessLanguage(text: string): string {
  const sample = text.slice(0, 5000)
  const rtl = sample.match(RTL_SCRIPT)?.length ?? 0
  const letters = sample.match(/\p{L}/gu)?.length ?? 1
  return rtl / letters > 0.3 ? 'fa' : 'en'
}

export function txtToFb2(text: string, title: string, language?: string | null): string {
  const clean = text.replace(/^﻿/, '').replace(/\r\n?/g, '\n')
  const paragraphs = clean.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
  const sections: string[] = []
  for (let i = 0; i < paragraphs.length; i += PARAGRAPHS_PER_SECTION) {
    const body = paragraphs.slice(i, i + PARAGRAPHS_PER_SECTION)
      .map((p) => `<p>${escapeXml(p).replace(/\n/g, ' ')}</p>`).join('')
    sections.push(`<section>${body}</section>`)
  }
  const lang = language || guessLanguage(clean)
  return `<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
<description><title-info><book-title>${escapeXml(title)}</book-title><lang>${escapeXml(lang)}</lang></title-info></description>
<body>${sections.join('') || '<section><p></p></section>'}</body>
</FictionBook>`
}
