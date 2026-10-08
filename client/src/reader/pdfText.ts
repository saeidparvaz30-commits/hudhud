// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Text view for PDFs. A PDF page is a picture of a page, which is unreadable on a
 * phone. Here the page's text runs (from pdf.js) are rebuilt into paragraphs and
 * written as FB2, one section per page, so foliate can reflow them like an EPUB
 * and page N in this view is page N in the page view.
 */
import { escapeXml, guessLanguage } from './txt'

export interface TextItem {
  str: string
  transform: number[]  // [a, b, c, d, x, y]
  width: number
  height: number
  hasEOL?: boolean
}

export interface Block { text: string; heading: boolean }

interface Line { text: string; x: number; right: number; y: number; size: number }

const median = (values: number[]) => {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.floor(sorted.length / 2)]
}

function toLines(items: TextItem[]): Line[] {
  const lines: Line[] = []
  for (const item of items) {
    if (!item.str) continue
    const [a, b, , , x, y] = item.transform
    const size = Math.hypot(a, b) || item.height || 10
    const last = lines.at(-1)
    if (last && Math.abs(last.y - y) < size * 0.5) {
      const gap = x - last.right
      const needsSpace = gap > size * 0.15 && !last.text.endsWith(' ') && !item.str.startsWith(' ')
      last.text += (needsSpace ? ' ' : '') + item.str
      last.right = Math.max(last.right, x + item.width)
      last.size = Math.max(last.size, size)
    } else {
      lines.push({ text: item.str, x, right: x + item.width, y, size })
    }
  }
  return lines
    .map((l) => ({ ...l, text: l.text.replace(/\s+/g, ' ').trim() }))
    .filter((l) => l.text && !/^\d{1,4}$/.test(l.text))  // blank lines, bare page numbers
}

function joinLines(previous: string, next: string): string {
  // "exam-" + "ple" is one hyphenated word; "well-known" stays as it is.
  if (/\p{L}-$/u.test(previous) && /^\p{Ll}/u.test(next)) return previous.slice(0, -1) + next
  return `${previous} ${next}`
}

/** Rebuild paragraphs and headings from one page's text runs. */
export function textItemsToBlocks(items: TextItem[]): Block[] {
  const lines = toLines(items)
  if (!lines.length) return []
  const bodySize = median(lines.map((l) => l.size))
  const gaps = lines.slice(1).map((l, i) => lines[i].y - l.y).filter((g) => g > 0)
  const lineGap = median(gaps) || bodySize * 1.2
  const left = Math.min(...lines.filter((l) => l.size <= bodySize * 1.1).map((l) => l.x))

  const blocks: Block[] = []
  let current: Block | null = null
  lines.forEach((line, i) => {
    const heading = line.size > bodySize * 1.25
    const gap = i ? lines[i - 1].y - line.y : 0
    const indented = !heading && line.x > left + bodySize * 1.2
    const startsNew = !current || heading || current.heading || gap > lineGap * 1.4
      || gap < 0 || indented
    if (startsNew) {
      current = { text: line.text, heading }
      blocks.push(current)
    } else if (current) {
      current.text = joinLines(current.text, line.text)
    }
  })
  return blocks
}

export function pagesToFb2(pages: Block[][], title: string, language?: string | null): string {
  const sections = pages.map((blocks) => {
    const body = blocks.length
      ? blocks.map((b) => b.heading ? `<subtitle>${escapeXml(b.text)}</subtitle>`
                                    : `<p>${escapeXml(b.text)}</p>`).join('')
      : '<p><emphasis>This page has no text. Switch to page view to see it.</emphasis></p>'
    return `<section>${body}</section>`
  })
  const sample = pages.flat().slice(0, 40).map((b) => b.text).join(' ')
  const lang = language || guessLanguage(sample)
  return `<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
<description><title-info><book-title>${escapeXml(title)}</book-title><lang>${escapeXml(lang)}</lang></title-info></description>
<body>${sections.join('') || '<section><p></p></section>'}</body>
</FictionBook>`
}

interface PdfJs {
  GlobalWorkerOptions: { workerSrc: string }
  getDocument(src: { data: ArrayBuffer; isEvalSupported: boolean; cMapUrl: string
                     standardFontDataUrl: string }): {
    promise: Promise<{ numPages: number; getPage(n: number): Promise<{
      getTextContent(): Promise<{ items: (TextItem | { type: string })[] }> }>
      destroy(): Promise<void> }>
  }
}

async function loadPdfJs(): Promise<PdfJs> {
  const base = new URL('/foliate-js/vendor/pdfjs/', window.location.href).href
  await import(/* @vite-ignore */ `${base}pdf.mjs`)
  const pdfjs = (globalThis as unknown as { pdfjsLib: PdfJs }).pdfjsLib
  pdfjs.GlobalWorkerOptions.workerSrc = `${base}pdf.worker.mjs`
  return pdfjs
}

/** Extract every page's text and build the text-view FB2. */
export async function pdfToFb2(blob: Blob, title: string, language: string | null,
                               onProgress?: (done: number, total: number) => void): Promise<string> {
  const pdfjs = await loadPdfJs()
  const base = new URL('/foliate-js/vendor/pdfjs/', window.location.href).href
  const doc = await pdfjs.getDocument({ data: await blob.arrayBuffer(), isEvalSupported: false,
                                        cMapUrl: `${base}cmaps/`,
                                        standardFontDataUrl: `${base}standard_fonts/` }).promise
  try {
    const pages: Block[][] = []
    for (let n = 1; n <= doc.numPages; n++) {
      const content = await (await doc.getPage(n)).getTextContent()
      pages.push(textItemsToBlocks(content.items.filter((i): i is TextItem => 'str' in i)))
      onProgress?.(n, doc.numPages)
    }
    return pagesToFb2(pages, title, language)
  } finally {
    await doc.destroy()
  }
}
