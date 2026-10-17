// SPDX-License-Identifier: AGPL-3.0-or-later
import { execFileSync } from 'node:child_process'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { type Page, expect, test } from '@playwright/test'
import { VAULT_DIR, hudhud } from './paths.mjs'

const PHRASE = 'the hoopoe led the birds across seven valleys'

function pairingUrl(): string {
  const [cmd, args] = hudhud(['pair', '--announce'])
  const out = execFileSync(cmd, args, { encoding: 'utf8' })
  const url = /HUDHUD_URL (\S+)/.exec(out)?.[1]
  if (!url) throw new Error(`no pairing URL in: ${out}`)
  return url
}

function book(): Buffer {
  const filler = 'A quiet paragraph about reading slowly and remembering where you stopped.'
  const paragraphs = Array.from({ length: 30 }, (_, i) => `${i + 1}. ${filler}`)
  paragraphs.splice(1, 0, `Long ago ${PHRASE}, looking for their king.`)
  return Buffer.from(paragraphs.join('\n\n'), 'utf8')
}

function vaultNotes(): string {
  const files = readdirSync(VAULT_DIR, { recursive: true, encoding: 'utf8' })
    .filter((f) => f.endsWith('.md'))
  return files.map((f) => readFileSync(join(VAULT_DIR, f), 'utf8')).join('\n')
}

/** Selects `text` inside whichever book frame shows it, as a reader's drag would. */
async function selectInBook(page: Page, text: string) {
  await expect.poll(async () => {
    for (const frame of page.frames()) {
      const selected = await frame.evaluate((needle) => {
        const walker = document.createTreeWalker(document.body ?? document, NodeFilter.SHOW_TEXT)
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          const at = node.textContent?.indexOf(needle) ?? -1
          if (at < 0) continue
          const range = document.createRange()
          range.setStart(node, at)
          range.setEnd(node, at + needle.length)
          const sel = document.getSelection()!
          sel.removeAllRanges()
          sel.addRange(range)
          document.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }))
          return true
        }
        return false
      }, text).catch(() => false)
      if (selected) return true
    }
    return false
  }, { timeout: 15_000 }).toBe(true)
}

test('pair, import, read, highlight, and the note reaches the vault', async ({ page }) => {
  await page.goto(pairingUrl())
  await expect(page.getByText('Your shelf is empty')).toBeVisible()

  await page.locator('input[type=file]').setInputFiles(
    { name: 'The Hoopoe.txt', mimeType: 'text/plain', buffer: book() })
  await page.getByRole('button', { name: /The Hoopoe/ }).first().click()
  await expect(page).toHaveURL(/\/read\//)

  await selectInBook(page, PHRASE)
  const popover = page.getByRole('dialog', { name: 'Highlight selection' })
  await expect(popover).toBeVisible()
  await popover.getByRole('button', { name: 'green highlight' }).click()

  await expect.poll(vaultNotes, { timeout: 20_000 }).toContain(PHRASE)
})

test('a second device pairs and receives the library, and stays paired', async ({ page }) => {
  await page.goto(pairingUrl())
  await expect(page.getByRole('button', { name: /The Hoopoe/ }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: /The Hoopoe/ }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Settings' })).toBeVisible()
})
