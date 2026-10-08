// SPDX-License-Identifier: AGPL-3.0-or-later
import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'app.hudhud.reader',
  appName: 'Hudhud',
  webDir: 'dist',
  server: {
    // The reader runs from http://localhost inside the app: still a secure context,
    // and it can reach both an HTTPS hub (Tailscale) and a plain-HTTP hub on the LAN.
    androidScheme: 'http',
    cleartext: true,
  },
  android: {
    allowMixedContent: true,
  },
}

export default config
