// SPDX-License-Identifier: AGPL-3.0-or-later
/** Picture highlights: find the picture under a tap, its caption, and its pixels. */

const MAX_SIDE = 2000

/** The picture element under a tap, if any (an <img>, or an inline SVG drawing). */
export function pictureAt(target: EventTarget | null): Element | null {
  const el = target as Element | null
  if (!el?.closest) return null
  return el.closest('img') ?? el.closest('svg')
}

const clean = (text: string | null | undefined) => (text ?? '').replace(/\s+/g, ' ').trim()

/** The caption a reader would use: <figcaption>, a "Figure ..." line right after, alt text. */
export function pictureCaption(picture: Element): string {
  const figure = picture.closest('figure')
  const caption = clean(figure?.querySelector('figcaption')?.textContent)
  if (caption) return caption
  // In a PDF's text view the caption is the paragraph after the image.
  let next: Element | null = (figure ?? picture).nextElementSibling
    ?? picture.parentElement?.nextElementSibling ?? null
  for (let i = 0; next && i < 2; i++, next = next.nextElementSibling) {
    const text = clean(next.textContent)
    if (/^(fig(ure)?\.?|table|chart|diagram|شکل|تصویر)\s*[\d٠-٩۰-۹]/i.test(text)) {
      return text.slice(0, 500)
    }
  }
  return clean(picture.getAttribute('alt')) || clean(picture.getAttribute('title'))
    || clean(picture.getAttribute('aria-label')) || 'Picture'
}

function drawToBlob(source: CanvasImageSource, width: number, height: number): Promise<Blob> {
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height, 1))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))
  const ctx = canvas.getContext('2d')
  if (!ctx) return Promise.reject(new Error('Cannot read the picture'))
  ctx.fillStyle = '#fff'  // transparent PNGs and SVGs get a page-white background
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height)
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Cannot read the picture'))),
                  'image/jpeg', 0.9))
}

/** The picture's pixels as a JPEG (any source format, inline SVG included). */
export async function pictureBlob(picture: Element): Promise<Blob> {
  if (picture instanceof picture.ownerDocument.defaultView!.HTMLImageElement) {
    const img = picture as HTMLImageElement
    if (!img.complete) await img.decode()
    return drawToBlob(img, img.naturalWidth, img.naturalHeight)
  }
  const svg = picture as SVGSVGElement
  const box = svg.getBoundingClientRect()
  const markup = new XMLSerializer().serializeToString(svg)
  const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml' }))
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    return drawToBlob(img, img.naturalWidth || box.width * 2, img.naturalHeight || box.height * 2)
  } finally {
    URL.revokeObjectURL(url)
  }
}
