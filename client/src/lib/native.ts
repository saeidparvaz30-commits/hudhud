// SPDX-License-Identifier: AGPL-3.0-or-later
import { Capacitor } from '@capacitor/core'

/** True inside the Android (or later iOS) app, false in a browser. */
export function isNativeApp(): boolean {
  return Capacitor.isNativePlatform()
}

export interface PairingLink { hubUrl: string; code: string; hubUrls: string[] }

/** The origin of an http(s) address, or null for anything else. */
function httpOrigin(text: string): string | null {
  try {
    const url = new URL(text)
    return /^https?:$/.test(url.protocol) ? url.origin : null
  } catch {
    return null
  }
}

/**
 * An invite link (https://hub/?pair=CODE&hub=OTHER...) split into the hub address, the
 * code and every address the hub listed.
 */
export function parsePairingLink(text: string): PairingLink | null {
  const hubUrl = httpOrigin(text.trim())
  if (!hubUrl) return null
  const params = new URL(text.trim()).searchParams
  const code = params.get('pair')
  if (!code) return null
  const others = params.getAll('hub').map(httpOrigin).filter((u): u is string => u !== null)
  return { hubUrl, code, hubUrls: [...new Set([hubUrl, ...others])] }
}

/** Open the camera and read an invite QR code. Null if cancelled or not an invite. */
export async function scanPairingCode(): Promise<PairingLink | null> {
  const { CapacitorBarcodeScanner, CapacitorBarcodeScannerTypeHint } =
    await import('@capacitor/barcode-scanner')
  const result = await CapacitorBarcodeScanner.scanBarcode({
    hint: CapacitorBarcodeScannerTypeHint.QR_CODE,
    scanInstructions: 'Point at the QR code in Settings > Add a device',
  })
  return parsePairingLink(result.ScanResult)
}
