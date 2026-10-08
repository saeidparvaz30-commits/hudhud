// SPDX-License-Identifier: AGPL-3.0-or-later
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

/**
 * Books are untrusted. foliate-js renders them in same-origin blob iframes with
 * scripts allowed, and blob documents inherit this page's policy, so allowing
 * scripts only from the app itself keeps a book's <script> from reading the
 * device token. connect-src stays open because the hub may live anywhere (R1).
 */
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "worker-src 'self' blob:",
  "style-src 'self' 'unsafe-inline' blob:",
  "img-src 'self' blob: data:",
  "font-src 'self' blob: data:",
  "media-src 'self' blob: data:",
  "frame-src 'self' blob:",
  "connect-src 'self' http: https: blob: data:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
].join('; ')

function contentSecurityPolicy(): Plugin {
  return {
    name: 'hudhud-csp',
    apply: 'build',  // the dev server injects inline scripts for hot reload
    transformIndexHtml: (html) => html.replace(
      '<head>',
      `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CONTENT_SECURITY_POLICY}" />`,
    ),
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), contentSecurityPolicy()],
  server: { host: true, port: 5173 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
