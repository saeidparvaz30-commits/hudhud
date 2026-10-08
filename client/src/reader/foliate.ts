// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The bridge to the vendored foliate-js (public/foliate-js, MIT). It is loaded at
 * runtime by URL so Vite leaves its own dynamic imports and PDF.js worker alone.
 */
import literataLatin from '@fontsource-variable/literata/files/literata-latin-wght-normal.woff2?url'
import literataLatinExt from '@fontsource-variable/literata/files/literata-latin-ext-wght-normal.woff2?url'
import vazirArabic from '@fontsource-variable/vazirmatn/files/vazirmatn-arabic-wght-normal.woff2?url'

import type { Book } from '../lib/types'
import { txtToFb2 } from './txt'

export interface RelocateDetail {
  fraction: number
  cfi: string
  location?: { current: number; next: number; total: number }
  tocItem?: { label?: string; href?: string }
  section?: { current: number; total: number }
}

export interface TocItem { label: string; href: string; subitems?: TocItem[] }

export interface FoliateBook {
  dir?: string
  toc?: TocItem[]
  metadata?: { title?: unknown; language?: string | string[] }
  rendition?: { layout?: string }
}

export interface FoliateRenderer extends HTMLElement {
  setStyles?(css: string): void
  next(): Promise<void>
  prev(): Promise<void>
}

export interface FoliateView extends HTMLElement {
  book: FoliateBook
  renderer: FoliateRenderer
  isFixedLayout: boolean
  lastLocation: RelocateDetail | null
  open(file: File): Promise<void>
  close(): void
  init(options: { lastLocation?: string | null; showTextStart?: boolean }): Promise<void>
  goTo(target: string | number): Promise<unknown>
  goToFraction(fraction: number): Promise<void>
  goLeft(): Promise<void>
  goRight(): Promise<void>
  prev(): Promise<void>
  next(): Promise<void>
  getCFI(index: number, range: Range): string
  resolveCFI(cfi: string): { index: number }
  addAnnotation(annotation: { value: string; color?: string }): Promise<unknown>
  deleteAnnotation(annotation: { value: string }): Promise<unknown>
  getSectionFractions(): number[]
}

interface OverlayerModule {
  Overlayer: { highlight: unknown; underline: unknown }
}

let loading: Promise<OverlayerModule> | null = null

/** Registers <foliate-view> and returns the Overlayer helpers. */
export function loadFoliate(): Promise<OverlayerModule> {
  loading ??= (async () => {
    const base = new URL('/foliate-js/', window.location.href).href
    await import(/* @vite-ignore */ `${base}view.js`)
    return (await import(/* @vite-ignore */ `${base}overlayer.js`)) as OverlayerModule
  })()
  return loading
}

const MIME: Record<string, string> = {
  epub: 'application/epub+zip',
  pdf: 'application/pdf',
  mobi: 'application/x-mobipocket-ebook',
  azw3: 'application/vnd.amazon.ebook',
  fb2: 'application/x-fictionbook+xml',
  cbz: 'application/vnd.comicbook+zip',
}

/** foliate picks a parser from the file name and type, so name the file honestly. */
export async function toFoliateFile(book: Book, blob: Blob): Promise<File> {
  if (book.format === 'txt') {
    const text = new TextDecoder('utf-8').decode(await blob.arrayBuffer())
    const fb2 = txtToFb2(text, book.title, book.language)
    return new File([fb2], `${book.id}.fb2`, { type: MIME.fb2 })
  }
  return new File([blob], `${book.id}.${book.format}`, { type: MIME[book.format] })
}

export interface ReadingStyle {
  fontScale: number  // 1 = 100%
  lineHeight: number
  justify: boolean
  colors: { paper: string; ink: string; accent: string; selection: string }
}

const absolute = (url: string) => new URL(url, window.location.href).href

/** CSS injected into each book document (it lives in an iframe, so fonts are declared here). */
export function bookCss(style: ReadingStyle): string {
  return `
@font-face { font-family: 'Hudhud Literata'; font-weight: 200 900; font-display: swap;
  src: url('${absolute(literataLatin)}') format('woff2'); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: 'Hudhud Literata'; font-weight: 200 900; font-display: swap;
  src: url('${absolute(literataLatinExt)}') format('woff2'); unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: 'Hudhud Vazirmatn'; font-weight: 100 900; font-display: swap;
  src: url('${absolute(vazirArabic)}') format('woff2'); unicode-range: U+0600-06FF, U+0750-077F, U+0870-088E, U+0890-0891, U+0897-08E1, U+08E3-08FF, U+200C-200E, U+2010-2011, U+204F, U+2E41, U+FB50-FDFF, U+FE70-FE74, U+FE76-FEFC; }
html {
  color: ${style.colors.ink} !important;
  background: transparent !important;
  font-size: ${Math.round(style.fontScale * 100)}% !important;
}
body, p, li, blockquote, dd, div, span {
  font-family: 'Hudhud Literata', 'Hudhud Vazirmatn', Georgia, serif;
}
body { color: ${style.colors.ink} !important; background: transparent !important; }
p, li, blockquote, dd {
  line-height: ${style.lineHeight} !important;
  text-align: ${style.justify ? 'justify' : 'start'};
  hyphens: auto;
  widows: 2;
  orphans: 2;
}
[align="center"] { text-align: center; }
a:link, a:visited { color: ${style.colors.accent}; }
::selection { background: ${style.colors.selection}; }
pre { white-space: pre-wrap !important; }
img, svg { max-width: 100%; height: auto; }
`
}

/** Solid colours: foliate's overlayer applies the opacity (--overlayer-highlight-opacity). */
export const HIGHLIGHT_CSS: Record<string, string> = {
  yellow: '#f2c94c',
  green: '#6fb05c',
  blue: '#569cd6',
  pink: '#e87497',
  purple: '#a078d2',
}
