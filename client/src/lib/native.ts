// SPDX-License-Identifier: AGPL-3.0-or-later
import { Capacitor } from '@capacitor/core'

/** True inside the Android (or later iOS) app, false in a browser. */
export function isNativeApp(): boolean {
  return Capacitor.isNativePlatform()
}

/** An invite link (https://hub/?pair=CODE) split into the hub address and the code. */
export function parsePairingLink(text: string): { hubUrl: string; code: string } | null {
  try {
    const url = new URL(text.trim())
    const code = url.searchParams.get('pair')
    if (!code || !/^https?:$/.test(url.protocol)) return null
    return { hubUrl: url.origin, code }
  } catch {
    return null
  }
}

/** Open the camera and read an invite QR code. Null if cancelled or not an invite. */
export async function scanPairingCode(): Promise<{ hubUrl: string; code: string } | null> {
  const { CapacitorBarcodeScanner, CapacitorBarcodeScannerTypeHint } =
    await import('@capacitor/barcode-scanner')
  const result = await CapacitorBarcodeScanner.scanBarcode({
    hint: CapacitorBarcodeScannerTypeHint.QR_CODE,
    scanInstructions: 'Point at the QR code in Settings > Add a device',
  })
  return parsePairingLink(result.ScanResult)
}
