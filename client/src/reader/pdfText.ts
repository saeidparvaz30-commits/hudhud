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

/** A paragraph or heading. `top` is its first line's top in PDF units (y grows upwards). */
export interface Block { text: string; heading: boolean; top?: number }

/** A figure cut from the rendered page, as base64 image data. */
export interface Figure { image: string; type: string; top: number }

export type PageItem = Block | Figure

/** A box in rendered-page pixels (y grows downwards). */
export interface Rect { x0: number; y0: number; x1: number; y1: number }

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
      current = { text: line.text, heading, top: line.y + line.size }
      blocks.push(current)
    } else if (current) {
      current.text = joinLines(current.text, line.text)
    }
  })
  return blocks
}

const isFigure = (item: PageItem): item is Figure => 'image' in item

/**
 * Where the figures are on a rendered page. `rowInk` counts, per pixel row, the
 * non-background pixels that are not under text: drawings and pictures. Rows of ink
 * close together form a band; a band counts as a figure when it is tall enough and
 * mostly graphics, so rules, specks and boxed sidebars full of text stay text.
 */
export function findFigureBands(rowInk: Uint32Array, textRects: Rect[], width: number,
                                height: number): Rect[] {
  // Thin arrows and dashed lines (2 px) hold a diagram's parts together; rows of a
  // diagram can sit a few lines apart; a figure is at least ~3% of the page tall.
  const minInk = 2
  const gapTolerance = Math.round(height * 0.035)
  const minHeight = Math.max(30, height * 0.03)
  const bands: Rect[] = []
  let current: Rect | null = null
  for (let row = 0; row < height; row++) {
    if (rowInk[row] < minInk) continue
    if (current && row - current.y1 <= gapTolerance) current.y1 = row + 1
    else {
      current = { x0: 0, x1: width, y0: row, y1: row + 1 }
      bands.push(current)
    }
  }
  const pad = 6
  return bands
    .filter((band) => band.y1 - band.y0 >= minHeight)
    .filter((band) => {
      const text = textRects.reduce((area, r) => {
        const h = Math.min(r.y1, band.y1) - Math.max(r.y0, band.y0)
        return h > 0 ? area + h * Math.max(0, r.x1 - r.x0) : area
      }, 0)
      return text / ((band.y1 - band.y0) * width) < 0.25
    })
    .map((band) => ({ ...band, y0: Math.max(0, band.y0 - pad), y1: Math.min(height, band.y1 + pad) }))
}

export function pagesToFb2(pages: PageItem[][], title: string, language?: string | null): string {
  const binaries: string[] = []
  const sections = pages.map((items, page) => {
    let figures = 0
    const body = items.map((item) => {
      if (isFigure(item)) {
        const id = `fig-${page}-${figures++}`
        binaries.push(`<binary id="${id}" content-type="${item.type}">${item.image}</binary>`)
        return `<image l:href="#${id}"/>`
      }
      return item.heading ? `<subtitle>${escapeXml(item.text)}</subtitle>`
        : `<p>${escapeXml(item.text)}</p>`
    }).join('')
    return `<section>${body
      || '<p><emphasis>This page has no text. Switch to page view to see it.</emphasis></p>'}</section>`
  })
  const sample = pages.flat().filter((i): i is Block => !isFigure(i)).slice(0, 40)
    .map((b) => b.text).join(' ')
  const lang = language || guessLanguage(sample)
  return `<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
<description><title-info><book-title>${escapeXml(title)}</book-title><lang>${escapeXml(lang)}</lang></title-info></description>
<body>${sections.join('') || '<section><p></p></section>'}</body>
${binaries.join('\n')}
</FictionBook>`
}

interface Viewport {
  width: number
  height: number
  scale: number
  transform: number[]
  convertToPdfPoint(x: number, y: number): [number, number]
}

interface PdfPage {
  getTextContent(): Promise<{ items: (TextItem | { type: string })[] }>
  getViewport(options: { scale: number }): Viewport
  render(options: { canvasContext: CanvasRenderingContext2D; viewport: Viewport }):
    { promise: Promise<void> }
  cleanup(): void
}

interface PdfJs {
  GlobalWorkerOptions: { workerSrc: string }
  Util: { transform(m1: number[], m2: number[]): number[] }
  getDocument(src: { data: ArrayBuffer; isEvalSupported: boolean; cMapUrl: string
                     standardFontDataUrl: string }): {
    promise: Promise<{ numPages: number; getPage(n: number): Promise<PdfPage>
      destroy(): Promise<void> }>
  }
}

const RENDER_SCALE = 1.5

const isBackground = (data: Uint8ClampedArray, i: number) =>
  data[i] > 232 && data[i + 1] > 232 && data[i + 2] > 232

/** Ink per row, not counting pixels under text. */
function inkRows(data: Uint8ClampedArray, width: number, height: number, text: Rect[]) {
  const masks: [number, number][][] = Array.from({ length: height }, () => [])
  for (const r of text) {
    for (let y = Math.max(0, Math.floor(r.y0)); y < Math.min(height, Math.ceil(r.y1)); y++) {
      masks[y].push([Math.floor(r.x0), Math.ceil(r.x1)])
    }
  }
  const rows = new Uint32Array(height)
  for (let y = 0; y < height; y++) {
    const mask = masks[y]
    let count = 0
    for (let x = 0; x < width; x++) {
      if (isBackground(data, (y * width + x) * 4)) continue
      if (mask.length && mask.some(([a, b]) => x >= a && x < b)) continue
      count++
    }
    rows[y] = count
  }
  return rows
}

/** Render a page, cut out its figures, and return them with the text that is not in them. */
async function pageItems(pdfjs: PdfJs, page: PdfPage): Promise<PageItem[]> {
  const content = await page.getTextContent()
  const items = content.items.filter((i): i is TextItem => 'str' in i && Boolean(i.str.trim()))
  const viewport = page.getViewport({ scale: RENDER_SCALE })
  const width = Math.ceil(viewport.width)
  const height = Math.ceil(viewport.height)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return textItemsToBlocks(items)
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, width, height)
  await page.render({ canvasContext: ctx, viewport }).promise

  const rects = items.map((item): Rect => {
    const m = pdfjs.Util.transform(viewport.transform, item.transform)
    const size = Math.hypot(m[2], m[3]) || item.height * viewport.scale
    return { x0: m[4], x1: m[4] + item.width * viewport.scale, y0: m[5] - size, y1: m[5] + size * 0.25 }
  })
  const data = ctx.getImageData(0, 0, width, height).data
  const bands = findFigureBands(inkRows(data, width, height, rects), rects, width, height)

  const figures: Figure[] = bands.map((band) => {
    // Trim the band to the columns that hold anything, with a little margin.
    let x0 = width
    let x1 = 0
    for (let y = band.y0; y < band.y1; y++) {
      for (let x = 0; x < width; x++) {
        if (!isBackground(data, (y * width + x) * 4)) {
          if (x < x0) x0 = x
          if (x > x1) x1 = x
        }
      }
    }
    x0 = Math.max(0, x0 - 6)
    x1 = Math.min(width, x1 + 7)
    const crop = document.createElement('canvas')
    crop.width = Math.max(1, x1 - x0)
    crop.height = band.y1 - band.y0
    crop.getContext('2d')?.drawImage(canvas, x0, band.y0, crop.width, crop.height, 0, 0,
                                    crop.width, crop.height)
    return { image: crop.toDataURL('image/jpeg', 0.85).split(',')[1], type: 'image/jpeg',
             top: viewport.convertToPdfPoint(0, band.y0)[1] }
  })
  page.cleanup()

  // Labels inside a figure belong to the picture, not to the text around it.
  const kept = items.filter((_, i) => {
    const middle = (rects[i].y0 + rects[i].y1) / 2
    return !bands.some((band) => middle >= band.y0 && middle <= band.y1)
  })
  const blocks: PageItem[] = textItemsToBlocks(kept)
  return [...blocks, ...figures].sort((a, b) => (b.top ?? 0) - (a.top ?? 0))
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
    const pages: PageItem[][] = []
    for (let n = 1; n <= doc.numPages; n++) {
      pages.push(await pageItems(pdfjs, await doc.getPage(n)))
      onProgress?.(n, doc.numPages)
    }
    return pagesToFb2(pages, title, language)
  } finally {
    await doc.destroy()
  }
}
